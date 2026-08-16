"""Pick Sony (gphoto2) when present, otherwise MacBook webcam."""

from __future__ import annotations

import logging
from typing import Literal, Optional, Protocol

from app.domain.models import CaptureResult
from app.infrastructure.camera.gphoto_camera import CameraError, GPhotoCamera
from app.infrastructure.camera.webcam_camera import WebcamCamera

logger = logging.getLogger(__name__)

CameraBackend = Literal["auto", "gphoto", "webcam"]
CameraSource = Literal["gphoto", "webcam"]


class Camera(Protocol):
    def check_connection(self) -> dict: ...

    def capture_photo(
        self,
        photo_id: Optional[str] = None,
        source: Optional[CameraSource] = None,
    ) -> CaptureResult: ...


class AutoCamera:
    """
    Facade over GPhotoCamera + WebcamCamera.

    ``backend``:
      - ``gphoto`` — force Sony USB
      - ``webcam`` — force MacBook camera
      - ``auto``   — Sony if connected, else webcam
    """

    def __init__(
        self,
        gphoto: GPhotoCamera,
        webcam: WebcamCamera,
        backend: CameraBackend = "auto",
    ) -> None:
        self.gphoto = gphoto
        self.webcam = webcam
        self.backend: CameraBackend = backend
        self._last_source: CameraSource | None = None

    @property
    def active_source(self) -> CameraSource:
        return self._resolve_source()

    def probe_sources(self) -> dict:
        """Independent status for both devices (for UI enable/disable)."""
        try:
            gphoto = self.gphoto.check_connection()
        except Exception as exc:  # noqa: BLE001
            gphoto = {"connected": False, "backend": "gphoto", "error": str(exc)}
        gphoto["source"] = "gphoto"

        try:
            webcam = self.webcam.check_connection()
        except Exception as exc:  # noqa: BLE001
            webcam = {"connected": False, "backend": "webcam", "error": str(exc)}
        webcam["source"] = "webcam"

        return {"gphoto": gphoto, "webcam": webcam}

    def check_connection(self) -> dict:
        sources = self.probe_sources()
        source = self._resolve_source(sources=sources)
        self._last_source = source
        status = dict(sources[source])
        status["source"] = source
        status["fallback"] = self.backend == "auto" and source == "webcam"
        status["sources"] = sources
        if status.get("connected") and status.get("fallback"):
            status["note"] = "Không thấy Sony — dùng camera MacBook."
        return status

    def capture_photo(
        self,
        photo_id: Optional[str] = None,
        source: Optional[CameraSource] = None,
    ) -> CaptureResult:
        use = source or self._resolve_source()
        if use not in ("gphoto", "webcam"):
            raise CameraError(f"Nguồn camera không hợp lệ: {use}")

        sources = self.probe_sources()
        if not sources[use].get("connected"):
            err = sources[use].get("error") or "chưa kết nối"
            label = "máy ảnh Sony" if use == "gphoto" else "webcam MacBook"
            raise CameraError(f"Không dùng được {label}: {err}")

        self._last_source = use
        logger.info("Capturing via %s (mode=%s)", use, self.backend)
        if use == "gphoto":
            return self.gphoto.capture_photo(photo_id=photo_id)
        return self.webcam.capture_photo(photo_id=photo_id)

    def _resolve_source(self, sources: dict | None = None) -> CameraSource:
        if self.backend == "webcam":
            return "webcam"
        if self.backend == "gphoto":
            return "gphoto"

        info = sources or self.probe_sources()
        if info["gphoto"].get("connected"):
            return "gphoto"
        return "webcam"
