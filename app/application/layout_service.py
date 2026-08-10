"""Template-based thermal layout renderer — POS58 384 px strip.

The print design (``assets/print_template.png``, 384x955 @ 203 DPI) already
carries every fixed element: logos, hard-fixed text and the photo/QR frames.
Rendering a print therefore means pasting the dithered photo block and the
two QR codes into that template, then converting to 1-bit for ESC/POS.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Sequence

import qrcode
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# Geometry measured from the design source (print_layout_full.svg, canvas 384x955)
TEMPLATE_SIZE = (384, 955)
PHOTO_BOX = (0, 90, 381, 510)           # x, y, w, h — full-bleed photo, frame line at col 381
QR_DOWNLOAD_BOX = (20, 805, 122, 122)   # left white patch — variable per print
QR_REGISTER_BOX = (243, 805, 122, 122)  # right white patch — fixed URL
QR_QUIET_PX = 4                       # in-box quiet zone kept around each QR
QR_MIN_MODULE_PX = 2                  # under ~0.25 mm/module phones stop scanning
TEXT_THRESHOLD = 160                  # template AA edges darker than this go solid black
DOWNLOAD_SCALE = 3                    # color photo (upload/download) resolution multiplier


class LayoutRenderer:
    """Paste one photo and the QR codes into the fixed print template."""

    def __init__(
        self,
        template_path: Path,
        register_qr_url: str = "",
        output_dir: Optional[Path] = None,
        portrait_aspect_w: int = 3,
        portrait_aspect_h: int = 4,
    ) -> None:
        self.register_qr_url = register_qr_url
        self.output_dir = output_dir
        # Bookkeeping for capture modes / status API — on paper the aspect is
        # dictated by PHOTO_BOX (3:4).
        self.portrait_aspect_w = portrait_aspect_w
        self.portrait_aspect_h = portrait_aspect_h
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        self._template = self._load_template(Path(template_path))

    def render(
        self,
        photo_paths: Path | Sequence[Path],
        qr_url: str,
        photo_id: Optional[str] = None,
        save: bool = True,
    ) -> Image.Image:
        """Compose template + photos + QR codes into the final 1-bit strip."""
        paths = self._normalize_paths(photo_paths)
        canvas = self._template.copy()

        photo = paths[0] if paths else None
        photo_block = self._photo_block(photo, (PHOTO_BOX[2], PHOTO_BOX[3]), as_gray=True)
        photo_block = photo_block.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")
        canvas.paste(photo_block, (PHOTO_BOX[0], PHOTO_BOX[1]))

        self._paste_qr(canvas, qr_url, QR_DOWNLOAD_BOX, label="download")
        if self.register_qr_url:
            self._paste_qr(canvas, self.register_qr_url, QR_REGISTER_BOX, label="register")

        strip = canvas.convert("1")
        if save and self.output_dir and photo_id:
            out = self.output_dir / f"{photo_id}_print.png"
            strip.save(out)
            logger.info("Saved print layout → %s", out)
        return strip

    def render_to_path(
        self,
        photo_paths: Path | Sequence[Path],
        qr_url: str,
        photo_id: str,
    ) -> Path:
        if not self.output_dir:
            raise ValueError("output_dir is required for render_to_path")
        self.render(photo_paths=photo_paths, qr_url=qr_url, photo_id=photo_id, save=True)
        return self.output_dir / f"{photo_id}_print.png"

    def render_photo_color(
        self,
        photo_paths: Path | Sequence[Path],
        photo_id: str,
    ) -> Path:
        """Save a color JPEG (guests download this) matching the print crop."""
        if not self.output_dir:
            raise ValueError("output_dir is required")
        paths = self._normalize_paths(photo_paths)
        size = (PHOTO_BOX[2] * DOWNLOAD_SCALE, PHOTO_BOX[3] * DOWNLOAD_SCALE)
        photo = self._photo_block(paths[0] if paths else None, size, as_gray=False)
        photos_dir = self.output_dir.parent / "photos"
        photos_dir.mkdir(parents=True, exist_ok=True)
        out = photos_dir / f"{photo_id}_full.jpg"
        photo.convert("RGB").save(out, quality=92)
        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_template(path: Path) -> Image.Image:
        if not path.exists():
            raise FileNotFoundError(
                f"Không tìm thấy template in: {path} — đặt print_template.png "
                f"({TEMPLATE_SIZE[0]}x{TEMPLATE_SIZE[1]}) vào assets/."
            )
        rgba = Image.open(path).convert("RGBA")
        if rgba.size != TEMPLATE_SIZE:
            raise ValueError(
                f"Template {path} phải đúng {TEMPLATE_SIZE[0]}x{TEMPLATE_SIZE[1]} px "
                f"(hiện là {rgba.size[0]}x{rgba.size[1]})."
            )
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        gray = Image.alpha_composite(white, rgba).convert("L")
        # Threshold instead of dithering so fixed text/frames stay crisp on thermal
        return gray.point(lambda v: 0 if v < TEXT_THRESHOLD else 255)

    @staticmethod
    def _normalize_paths(photo_paths: Path | Sequence[Path]) -> list[Path]:
        if isinstance(photo_paths, Path):
            return [photo_paths]
        return [Path(p) for p in photo_paths]

    @staticmethod
    def _photo_block(
        photo_path: Optional[Path],
        size: tuple[int, int],
        as_gray: bool,
    ) -> Image.Image:
        """One photo center-cropped to fill ``size`` (white block if missing)."""
        mode = "L" if as_gray else "RGB"
        fill = 255 if as_gray else (255, 255, 255)
        if photo_path is None or not Path(photo_path).exists():
            return Image.new(mode, size, color=fill)
        photo = Image.open(photo_path)
        photo = ImageOps.exif_transpose(photo).convert("RGB")
        fitted = ImageOps.fit(photo, size, method=Image.Resampling.LANCZOS)
        if not as_gray:
            return fitted
        # Autocontrast gives the dithered result more punch on thermal paper
        return ImageOps.autocontrast(fitted.convert("L"), cutoff=2)

    def _paste_qr(
        self,
        canvas: Image.Image,
        url: str,
        box: tuple[int, int, int, int],
        label: str,
    ) -> None:
        x, y, w, h = box
        qr = qrcode.QRCode(
            # EC level L keeps the module grid as small as possible — the
            # template QR patch is only ~7.8 mm wide.
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=0,  # the white patch itself is the quiet zone
        )
        qr.add_data(url)
        qr.make(fit=True)
        modules = qr.modules_count
        scale = max(1, (min(w, h) - 2 * QR_QUIET_PX) // modules)
        if scale < QR_MIN_MODULE_PX:
            logger.warning(
                "QR %s: URL %d ký tự → %dx%d modules, chỉ đạt %d px/module — "
                "nguy cơ không quét được, hãy rút gọn URL!",
                label,
                len(url),
                modules,
                modules,
                scale,
            )
        img = qr.make_image(fill_color="black", back_color="white").convert("L")
        img = img.resize((modules * scale, modules * scale), Image.Resampling.NEAREST)

        canvas.paste(255, (x, y, x + w, y + h))  # wipe the placeholder QR
        canvas.paste(img, (x + (w - img.width) // 2, y + (h - img.height) // 2))
