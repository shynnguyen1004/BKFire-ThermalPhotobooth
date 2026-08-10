"""Pick Sony (gphoto2) when present, otherwise MacBook webcam."""

from __future__ import annotations

import logging
from typing import Literal, Optional, Protocol

from app.domain.models import CaptureResult
from app.infrastructure.camera.gphoto_camera import CameraError, GPhotoCamera
from app.infrastructure.camera.webcam_camera import WebcamCamera

logger = logging.getLogger(__name__)

CameraBackend = Literal["auto", "gphoto", "webcam"]


class Camera(Protocol):
    def check_connection(self) -> dict: ...

    def capture_photo(self, photo_id: Optional[str] = None) -> CaptureResult: ...


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
        self._last_source: Literal["gphoto", "webcam"] | None = None

    @property
    def active_source(self) -> Literal["gphoto", "webcam"]:
        return self._resolve_source()

    def check_connection(self) -> dict:
        source = self._resolve_source()
        self._last_source = source
        if source == "gphoto":
            status = self.gphoto.check_connection()
            status["source"] = "gphoto"
            status["fallback"] = False
            return status

        status = self.webcam.check_connection()
        status["source"] = "webcam"
        status["fallback"] = self.backend == "auto"
        if status.get("connected") and self.backend == "auto":
            status["note"] = "Không thấy Sony — dùng camera MacBook (1 tấm 3:2 dọc)."
        return status

    def capture_photo(self, photo_id: Optional[str] = None) -> CaptureResult:
        source = self._resolve_source()
        self._last_source = source
        logger.info("Capturing via %s (mode=%s)", source, self.backend)
        if source == "gphoto":
            return self.gphoto.capture_photo(photo_id=photo_id)
        return self.webcam.capture_photo(photo_id=photo_id)

    def _resolve_source(self) -> Literal["gphoto", "webcam"]:
        if self.backend == "webcam":
            return "webcam"
        if self.backend == "gphoto":
            return "gphoto"

        try:
            status = self.gphoto.check_connection()
            if status.get("connected"):
                return "gphoto"
        except CameraError as exc:
            logger.info("gphoto unavailable, falling back to webcam: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.info("gphoto check failed, falling back to webcam: %s", exc)
        return "webcam"
