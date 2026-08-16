"""Subject cutout — remove background and composite onto white."""

from __future__ import annotations

import logging
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

_SESSION = None
_REMBG_AVAILABLE: Optional[bool] = None


def rembg_available() -> bool:
    global _REMBG_AVAILABLE
    if _REMBG_AVAILABLE is None:
        try:
            import rembg  # noqa: F401

            _REMBG_AVAILABLE = True
        except ImportError:
            _REMBG_AVAILABLE = False
            logger.warning(
                "rembg chưa cài — bỏ qua tách nền. Chạy: pip install rembg onnxruntime"
            )
    return _REMBG_AVAILABLE


def _session():
    global _SESSION
    if _SESSION is None:
        from rembg import new_session

        # Human-focused model — tốt hơn u2net generic cho photobooth
        _SESSION = new_session("u2net_human_seg")
        logger.info("Loaded rembg session: u2net_human_seg")
    return _SESSION


def cutout_on_white(photo: Image.Image) -> Image.Image:
    """Return RGB image with subject on solid white background.

    Falls back to the original RGB photo if rembg is unavailable or fails.
    """
    rgb = photo.convert("RGB")
    if not rembg_available():
        return rgb
    try:
        from rembg import remove

        rgba = remove(rgb, session=_session())
        if not isinstance(rgba, Image.Image):
            rgba = Image.open(rgba).convert("RGBA")  # type: ignore[arg-type]
        else:
            rgba = rgba.convert("RGBA")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(white, rgba).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Tách nền thất bại, giữ ảnh gốc: %s", exc)
        return rgb
