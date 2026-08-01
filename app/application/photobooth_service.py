"""Orchestrates Capture → Layout → Print for one booth session."""

from __future__ import annotations

import logging
from pathlib import Path

from app.application.layout_service import LayoutRenderer
from app.domain.models import PrintJobRequest, SessionResult
from app.infrastructure.camera.gphoto_camera import CameraError, GPhotoCamera
from app.infrastructure.printer.pos58_printer import POS58Printer, PrinterError
from app.infrastructure.storage.file_storage import FileStorage

logger = logging.getLogger(__name__)


class PhotoboothService:
    def __init__(
        self,
        camera: GPhotoCamera,
        layout: LayoutRenderer,
        printer: POS58Printer,
        storage: FileStorage,
    ) -> None:
        self.camera = camera
        self.layout = layout
        self.printer = printer
        self.storage = storage

    def status(self) -> dict:
        camera_status: dict
        try:
            camera_status = self.camera.check_connection()
        except CameraError as exc:
            camera_status = {"connected": False, "error": str(exc)}
        return {
            "camera": camera_status,
            "printer": self.printer.check_connection(),
        }

    def capture_and_print(self, request: PrintJobRequest) -> SessionResult:
        photo_id = request.photo_id or SessionResult.new_id()
        qr_url = request.qr_base_url.replace("{id}", photo_id)

        logger.info("Session %s — faculty=%s", photo_id, request.faculty)

        capture = self.camera.capture_photo(photo_id=photo_id)
        archived = self.storage.archive_photo(capture.local_path, photo_id)

        layout_path = self.layout.render_to_path(
            photo_path=archived,
            faculty=request.faculty,
            qr_url=qr_url,
            photo_id=photo_id,
            timestamp=capture.captured_at,
        )

        printed = False
        message = "Đã chụp & render layout."
        try:
            self.printer.print_image(layout_path)
            printed = True
            message = "Đã chụp, render và gửi lệnh in thành công."
        except PrinterError as exc:
            message = f"Đã chụp & render, nhưng in thất bại: {exc}"
            logger.exception("Print failed for %s", photo_id)

        return SessionResult(
            photo_id=photo_id,
            faculty=request.faculty,
            source_path=archived,
            layout_path=layout_path,
            qr_url=qr_url,
            printed=printed,
            message=message,
            captured_at=capture.captured_at,
        )

    def reprint(self, photo_id: str, faculty: str, qr_base_url: str) -> SessionResult:
        """Re-render + print an already archived photo."""
        source = self.storage.get_photo(photo_id)
        if source is None:
            raise FileNotFoundError(f"Không tìm thấy ảnh id={photo_id}")

        qr_url = qr_base_url.replace("{id}", photo_id)
        layout_path = self.layout.render_to_path(
            photo_path=source,
            faculty=faculty,
            qr_url=qr_url,
            photo_id=photo_id,
        )
        self.printer.print_image(layout_path)
        return SessionResult(
            photo_id=photo_id,
            faculty=faculty,
            source_path=source,
            layout_path=layout_path,
            qr_url=qr_url,
            printed=True,
            message="In lại thành công.",
        )

    def demo_from_image(
        self,
        image_path: Path,
        faculty: str,
        qr_base_url: str,
    ) -> SessionResult:
        """Dry pipeline using an existing JPEG (no camera) — useful for layout testing."""
        photo_id = SessionResult.new_id()
        archived = self.storage.archive_photo(image_path, photo_id)
        qr_url = qr_base_url.replace("{id}", photo_id)
        layout_path = self.layout.render_to_path(
            photo_path=archived,
            faculty=faculty,
            qr_url=qr_url,
            photo_id=photo_id,
        )
        printed = False
        message = "Demo layout đã render."
        try:
            self.printer.print_image(layout_path)
            printed = True
            message = "Demo: render + in thành công."
        except PrinterError as exc:
            message = f"Demo: render OK, in thất bại: {exc}"
        return SessionResult(
            photo_id=photo_id,
            faculty=faculty,
            source_path=archived,
            layout_path=layout_path,
            qr_url=qr_url,
            printed=printed,
            message=message,
        )
