"""Thermal layout renderer — 384 px POS58 strip with Floyd–Steinberg dithering."""

from __future__ import annotations

import logging
import textwrap
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

# Layout constants tuned for 58 mm / 384 px @ 203 DPI
WIDTH = 384
MARGIN = 12
GAP = 10
HEADER_H = 72
QR_SIZE = 120
FOOTER_PAD = 8


class LayoutRenderer:
    """Compose logo + photo + faculty + QR into a dithered 1-bit strip."""

    def __init__(
        self,
        width: int = WIDTH,
        logo_path: Optional[Path] = None,
        org_name: str = "BK FIRE",
        output_dir: Optional[Path] = None,
    ) -> None:
        self.width = width
        self.logo_path = logo_path
        self.org_name = org_name
        self.output_dir = output_dir
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def render(
        self,
        photo_path: Path,
        faculty: str,
        qr_url: str,
        timestamp: Optional[datetime] = None,
        photo_id: Optional[str] = None,
        save: bool = True,
    ) -> Image.Image:
        """
        Build full strip and apply Floyd–Steinberg dithering to mode ``1``.

        Returns the dithered Pillow image (mode ``1``).
        """
        ts = timestamp or datetime.now()
        header = self._build_header(ts)
        body = self._build_body(photo_path)
        footer = self._build_footer(faculty, qr_url)

        total_h = header.height + GAP + body.height + GAP + footer.height
        canvas = Image.new("L", (self.width, total_h), color=255)
        y = 0
        canvas.paste(header, (0, y))
        y += header.height + GAP
        canvas.paste(body, (0, y))
        y += body.height + GAP
        canvas.paste(footer, (0, y))

        # Separator rules (black hairlines) before dither
        draw = ImageDraw.Draw(canvas)
        draw.line([(MARGIN, header.height + GAP // 2), (self.width - MARGIN, header.height + GAP // 2)], fill=0, width=1)
        body_end = header.height + GAP + body.height
        draw.line([(MARGIN, body_end + GAP // 2), (self.width - MARGIN, body_end + GAP // 2)], fill=0, width=1)

        # REQUIRED: Floyd–Steinberg dithering for thermal B&W grain
        dithered = canvas.convert("1", dither=Image.Dither.FLOYDSTEINBERG)

        if save and self.output_dir and photo_id:
            out = self.output_dir / f"{photo_id}_print.png"
            dithered.save(out)
            logger.info("Saved dithered layout → %s", out)

        return dithered

    def render_to_path(
        self,
        photo_path: Path,
        faculty: str,
        qr_url: str,
        photo_id: str,
        timestamp: Optional[datetime] = None,
    ) -> Path:
        if not self.output_dir:
            raise ValueError("output_dir is required for render_to_path")
        img = self.render(
            photo_path=photo_path,
            faculty=faculty,
            qr_url=qr_url,
            timestamp=timestamp,
            photo_id=photo_id,
            save=True,
        )
        out = self.output_dir / f"{photo_id}_print.png"
        img.save(out)
        return out

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _build_header(self, ts: datetime) -> Image.Image:
        h = HEADER_H
        img = Image.new("L", (self.width, h), color=255)
        draw = ImageDraw.Draw(img)

        logo = self._load_logo(max_h=h - 16)
        x = MARGIN
        if logo is not None:
            img.paste(logo, (x, (h - logo.height) // 2))
            x += logo.width + 10
        else:
            font_brand = self._font(22, bold=True)
            draw.text((x, 12), self.org_name, fill=0, font=font_brand)
            x += draw.textlength(self.org_name, font=font_brand) + 10

        font_ts = self._font(14)
        ts_text = ts.strftime("%Y-%m-%d %H:%M:%S")
        tw = draw.textlength(ts_text, font=font_ts)
        draw.text((self.width - MARGIN - tw, (h - 18) // 2), ts_text, fill=0, font=font_ts)
        return img

    def _build_body(self, photo_path: Path) -> Image.Image:
        photo = Image.open(photo_path).convert("RGB")
        # Center-crop to a pleasant portrait-ish strip then fit width
        target_w = self.width - 2 * MARGIN
        # Aim ~4:3 after crop for booth feel, then scale to width
        photo = ImageOps.fit(photo, (target_w, int(target_w * 1.15)), method=Image.Resampling.LANCZOS)

        frame_h = photo.height + 2 * MARGIN
        frame = Image.new("L", (self.width, frame_h), color=255)
        gray = ImageOps.grayscale(photo)
        frame.paste(gray, (MARGIN, MARGIN))
        return frame

    def _build_footer(self, faculty: str, qr_url: str) -> Image.Image:
        qr = self._make_qr(qr_url, QR_SIZE)
        font = self._font(15)
        font_small = self._font(11)

        # Wrap faculty name to left column
        text_col_w = self.width - QR_SIZE - 3 * MARGIN
        lines = textwrap.wrap(faculty, width=22) or [faculty]
        line_h = 20
        text_block_h = max(len(lines) * line_h, 40)
        h = max(QR_SIZE, text_block_h) + 2 * FOOTER_PAD + 28

        img = Image.new("L", (self.width, h), color=255)
        draw = ImageDraw.Draw(img)

        y = FOOTER_PAD
        draw.text((MARGIN, y), "Khoa / Ngành:", fill=0, font=font_small)
        y += 16
        for line in lines[:4]:
            draw.text((MARGIN, y), line, fill=0, font=font)
            y += line_h

        # QR on the right
        qr_x = self.width - MARGIN - QR_SIZE
        qr_y = FOOTER_PAD
        img.paste(qr, (qr_x, qr_y))

        # Tiny URL hint under QR (truncated)
        hint = qr_url if len(qr_url) <= 36 else qr_url[:33] + "..."
        hint_w = draw.textlength(hint, font=font_small)
        draw.text(
            (max(MARGIN, (self.width - hint_w) // 2), h - 18),
            hint,
            fill=0,
            font=font_small,
        )
        return img

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_logo(self, max_h: int) -> Optional[Image.Image]:
        if not self.logo_path or not Path(self.logo_path).exists():
            logger.warning("logo.png not found at %s — using text brand", self.logo_path)
            return None
        logo = Image.open(self.logo_path).convert("RGBA")
        # Composite onto white so dither sees clean edges
        bg = Image.new("RGBA", logo.size, (255, 255, 255, 255))
        logo = Image.alpha_composite(bg, logo).convert("L")
        ratio = max_h / logo.height
        new_size = (max(1, int(logo.width * ratio)), max_h)
        # Cap width so timestamp still fits
        max_w = self.width // 2
        if new_size[0] > max_w:
            ratio = max_w / logo.width
            new_size = (max_w, max(1, int(logo.height * ratio)))
        return logo.resize(new_size, Image.Resampling.LANCZOS)

    def _make_qr(self, url: str, size: int) -> Image.Image:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=1,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("L")
        return img.resize((size, size), Image.Resampling.NEAREST)

    def _font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/SFNSMono.ttf",
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
        return ImageFont.load_default()


def dithered_to_png_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.convert("1").save(buf, format="PNG")
    return buf.getvalue()
