"""Orchestrates burst capture → collage → Cloudinary → print."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

from app.application.layout_service import LayoutRenderer
from app.domain.models import CaptureResult, PrintJobRequest, SessionResult
from app.infrastructure.camera.gphoto_camera import CameraError
from app.infrastructure.printer.pos58_printer import POS58Printer, PrinterError
from app.infrastructure.storage.cloudinary_storage import CloudinaryError, CloudinaryStorage
from app.infrastructure.storage.file_storage import FileStorage

logger = logging.getLogger(__name__)


class _Camera(Protocol):
    def check_connection(self) -> dict: ...

    def capture_photo(self, photo_id: Optional[str] = None) -> CaptureResult: ...

    @property
    def active_source(self) -> str: ...


@dataclass(frozen=True)
class CaptureMode:
    burst_count: int
    burst_interval_sec: float
    grid_cols: int
    grid_rows: int
    portrait_aspect_w: int
    portrait_aspect_h: int


class PhotoboothService:
    def __init__(
        self,
        camera: _Camera,
        layout: LayoutRenderer,
        printer: POS58Printer,
        storage: FileStorage,
        cloudinary: Optional[CloudinaryStorage] = None,
        qr_base_url: str = "",
        gphoto_mode: CaptureMode | None = None,
        webcam_mode: CaptureMode | None = None,
        burst_count: int = 4,
        burst_interval_sec: float = 3.0,
    ) -> None:
        self.camera = camera
        self.layout = layout
        self.printer = printer
        self.storage = storage
        self.cloudinary = cloudinary
        self.qr_base_url = qr_base_url
        self.gphoto_mode = gphoto_mode or CaptureMode(
            burst_count=burst_count,
            burst_interval_sec=burst_interval_sec,
            grid_cols=layout.grid_cols,
            grid_rows=layout.grid_rows,
            portrait_aspect_w=layout.portrait_aspect_w,
            portrait_aspect_h=layout.portrait_aspect_h,
        )
        self.webcam_mode = webcam_mode or CaptureMode(
            burst_count=1,
            burst_interval_sec=0.0,
            grid_cols=1,
            grid_rows=1,
            portrait_aspect_w=3,
            portrait_aspect_h=4,
        )
        self._apply_mode(self.gphoto_mode)

    def status(self) -> dict:
        camera_status: dict
        try:
            camera_status = self.camera.check_connection()
        except CameraError as exc:
            camera_status = {"connected": False, "error": str(exc)}

        source = camera_status.get("source") or getattr(self.camera, "active_source", "gphoto")
        mode = self._mode_for(str(source))
        self._apply_mode(mode)

        cloud = self.cloudinary.status() if self.cloudinary else {"enabled": False}
        return {
            "camera": camera_status,
            "printer": self.printer.check_connection(),
            "cloudinary": cloud,
            "burst": {
                "count": self.burst_count,
                "interval_sec": self.burst_interval_sec,
                "grid": f"{self.layout.grid_cols}x{self.layout.grid_rows}",
                "aspect": f"{self.layout.portrait_aspect_w}:{self.layout.portrait_aspect_h}",
                "source": source,
            },
        }

    def capture_and_print(self, request: PrintJobRequest) -> SessionResult:
        source = getattr(self.camera, "active_source", "gphoto")
        mode = self._mode_for(str(source))
        self._apply_mode(mode)

        session_id = request.photo_id or SessionResult.new_id()
        logger.info(
            "Session %s — faculty=%s — source=%s — burst %sx%.1fs — grid %sx%s — aspect %s:%s",
            session_id,
            request.faculty,
            source,
            self.burst_count,
            self.burst_interval_sec,
            self.layout.grid_cols,
            self.layout.grid_rows,
            self.layout.portrait_aspect_w,
            self.layout.portrait_aspect_h,
        )

        frame_paths = self._capture_burst(session_id)
        collage_path = self.layout.render_collage_color(frame_paths, session_id)
        # Also keep a convenience copy as session.jpg (first frame alias for /photos/{id}.jpg)
        main_photo = self.storage.archive_photo(collage_path, session_id)

        cloudinary_url: str | None = None
        # QR luôn dùng link ngắn — ô QR trên template chỉ 62 px, dán thẳng
        # secure_url Cloudinary (~95 ký tự) sẽ không quét được.
        qr_url = self._fallback_qr(request.qr_base_url, session_id)
        upload_note = ""

        if self.cloudinary and self.cloudinary.enabled:
            try:
                cloudinary_url = self.cloudinary.upload_photo(collage_path, f"{session_id}_grid")
            except CloudinaryError as exc:
                logger.exception("Cloudinary upload failed for %s", session_id)
                upload_note = f" Upload Cloudinary lỗi: {exc}"
        else:
            upload_note = " (Cloudinary chưa cấu hình — ảnh chỉ có trên máy local)"

        layout_path = self.layout.render_to_path(
            photo_paths=frame_paths,
            qr_url=qr_url,
            photo_id=session_id,
        )

        shot_label = f"{self.burst_count} tấm" if self.burst_count > 1 else "1 tấm"
        printed = False
        message = f"Đã chụp {shot_label} ({source}) & render layout.{upload_note}"
        try:
            self.printer.print_image(layout_path)
            printed = True
            message = f"Đã chụp {shot_label} ({source}), upload, in thành công.{upload_note}"
        except PrinterError as exc:
            message = f"Đã chụp & render, nhưng in thất bại: {exc}.{upload_note}"
            logger.exception("Print failed for %s", session_id)

        return SessionResult(
            photo_id=session_id,
            faculty=request.faculty,
            source_path=main_photo,
            layout_path=layout_path,
            qr_url=qr_url,
            printed=printed,
            message=message,
            cloudinary_url=cloudinary_url,
            frame_paths=frame_paths,
        )

    def _capture_burst(self, session_id: str) -> list[Path]:
        frames: list[Path] = []
        for i in range(1, self.burst_count + 1):
            frame_id = f"{session_id}_f{i}"
            logger.info("Burst %s/%s — capturing %s", i, self.burst_count, frame_id)
            capture = self.camera.capture_photo(photo_id=frame_id)
            archived = self.storage.archive_frame(capture.local_path, session_id, i)
            frames.append(archived)
            if i < self.burst_count and self.burst_interval_sec > 0:
                logger.info("Waiting %.1fs before next shot", self.burst_interval_sec)
                time.sleep(self.burst_interval_sec)
        return frames

    def reprint(self, photo_id: str, faculty: str, qr_base_url: str = "") -> SessionResult:
        frames = self.storage.get_session_frames(photo_id)
        if not frames:
            source = self.storage.get_photo(photo_id)
            if source is None:
                raise FileNotFoundError(f"Không tìm thấy ảnh id={photo_id}")
            frames = [source]

        # Match layout to how many frames we have
        if len(frames) == 1:
            self._apply_mode(self.webcam_mode)
        else:
            self._apply_mode(self.gphoto_mode)

        cloudinary_url: str | None = None
        qr_url = self._fallback_qr(qr_base_url, photo_id)
        if self.cloudinary and self.cloudinary.enabled:
            collage = self.layout.render_collage_color(frames, photo_id)
            cloudinary_url = self.cloudinary.upload_photo(collage, f"{photo_id}_grid")

        layout_path = self.layout.render_to_path(
            photo_paths=frames,
            qr_url=qr_url,
            photo_id=photo_id,
        )
        self.printer.print_image(layout_path)
        return SessionResult(
            photo_id=photo_id,
            faculty=faculty,
            source_path=frames[0],
            layout_path=layout_path,
            qr_url=qr_url,
            printed=True,
            message="In lại thành công.",
            cloudinary_url=cloudinary_url,
            frame_paths=frames,
        )

    def demo_from_image(
        self,
        image_path: Path,
        faculty: str,
        qr_base_url: str = "",
    ) -> SessionResult:
        """Demo with one image repeated across the configured grid."""
        session_id = SessionResult.new_id()
        frames = [
            self.storage.archive_frame(image_path, session_id, i)
            for i in range(1, self.burst_count + 1)
        ]
        collage_path = self.layout.render_collage_color(frames, session_id)
        main_photo = self.storage.archive_photo(collage_path, session_id)

        cloudinary_url: str | None = None
        qr_url = self._fallback_qr(qr_base_url, session_id)
        if self.cloudinary and self.cloudinary.enabled:
            try:
                cloudinary_url = self.cloudinary.upload_photo(collage_path, f"{session_id}_grid")
            except CloudinaryError as exc:
                logger.warning("Demo Cloudinary upload failed: %s", exc)

        layout_path = self.layout.render_to_path(
            photo_paths=frames,
            qr_url=qr_url,
            photo_id=session_id,
        )
        printed = False
        message = "Demo đã render."
        try:
            self.printer.print_image(layout_path)
            printed = True
            message = "Demo: layout + in thành công."
        except PrinterError as exc:
            message = f"Demo: render OK, in thất bại: {exc}"
        return SessionResult(
            photo_id=session_id,
            faculty=faculty,
            source_path=main_photo,
            layout_path=layout_path,
            qr_url=qr_url,
            printed=printed,
            message=message,
            cloudinary_url=cloudinary_url,
            frame_paths=frames,
        )

    def _mode_for(self, source: str) -> CaptureMode:
        return self.webcam_mode if source == "webcam" else self.gphoto_mode

    def _apply_mode(self, mode: CaptureMode) -> None:
        self.burst_count = mode.burst_count
        self.burst_interval_sec = mode.burst_interval_sec
        self.layout.grid_cols = mode.grid_cols
        self.layout.grid_rows = mode.grid_rows
        self.layout.portrait_aspect_w = mode.portrait_aspect_w
        self.layout.portrait_aspect_h = mode.portrait_aspect_h

    def _fallback_qr(self, request_base: str, photo_id: str) -> str:
        base = (request_base or self.qr_base_url or "").strip()
        if "{id}" in base:
            return base.replace("{id}", photo_id)
        if base:
            return f"{base.rstrip('/')}/{photo_id}"
        return f"https://res.cloudinary.com/pending/image/upload/{photo_id}_grid.jpg"
