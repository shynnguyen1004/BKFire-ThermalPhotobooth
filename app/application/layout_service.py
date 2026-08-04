"""Thermal layout renderer — 384 px POS58 strip with Floyd–Steinberg dithering."""

from __future__ import annotations

import logging
import textwrap
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional, Sequence

import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

# Layout constants tuned for 58 mm / 384 px @ 203 DPI
WIDTH = 384
MARGIN = 12
GAP = 8
HEADER_H = 72
QR_SIZE = 120
FOOTER_PAD = 8
CELL_GAP = 6


class LayoutRenderer:
    """Compose logo + photo grid + faculty + QR into a dithered 1-bit strip."""

    def __init__(
        self,
        width: int = WIDTH,
        logo_path: Optional[Path] = None,
        org_name: str = "BK FIRE",
        output_dir: Optional[Path] = None,
        grid_cols: int = 2,
        grid_rows: int = 2,
        portrait_aspect_w: int = 3,
        portrait_aspect_h: int = 4,
    ) -> None:
        self.width = width
        self.logo_path = logo_path
        self.org_name = org_name
        self.output_dir = output_dir
        self.grid_cols = grid_cols
        self.grid_rows = grid_rows
        self.portrait_aspect_w = portrait_aspect_w
        self.portrait_aspect_h = portrait_aspect_h
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def render(
        self,
        photo_paths: Path | Sequence[Path],
        faculty: str,
        qr_url: str,
        timestamp: Optional[datetime] = None,
        photo_id: Optional[str] = None,
        save: bool = True,
    ) -> Image.Image:
        """
        Build full strip (header + portrait grid + footer) and apply
        Floyd–Steinberg dithering to mode ``1``.
        """
        paths = self._normalize_paths(photo_paths)
        ts = timestamp or datetime.now()
        header = self._build_header(ts)
        body = self._build_grid_body(paths)
        footer = self._build_footer(faculty, qr_url)

        total_h = header.height + GAP + body.height + GAP + footer.height
        canvas = Image.new("L", (self.width, total_h), color=255)
        y = 0
        canvas.paste(header, (0, y))
        y += header.height + GAP
        canvas.paste(body, (0, y))
        y += body.height + GAP
        canvas.paste(footer, (0, y))

        draw = ImageDraw.Draw(canvas)
        draw.line(
            [(MARGIN, header.height + GAP // 2), (self.width - MARGIN, header.height + GAP // 2)],
            fill=0,
            width=1,
        )
        body_end = header.height + GAP + body.height
        draw.line(
            [(MARGIN, body_end + GAP // 2), (self.width - MARGIN, body_end + GAP // 2)],
            fill=0,
            width=1,
        )

        dithered = canvas.convert("1", dither=Image.Dither.FLOYDSTEINBERG)

        if save and self.output_dir and photo_id:
            out = self.output_dir / f"{photo_id}_print.png"
            dithered.save(out)
            logger.info("Saved dithered layout → %s", out)

        return dithered

    def render_to_path(
        self,
        photo_paths: Path | Sequence[Path],
        faculty: str,
        qr_url: str,
        photo_id: str,
        timestamp: Optional[datetime] = None,
    ) -> Path:
        if not self.output_dir:
            raise ValueError("output_dir is required for render_to_path")
        img = self.render(
            photo_paths=photo_paths,
            faculty=faculty,
            qr_url=qr_url,
            timestamp=timestamp,
            photo_id=photo_id,
            save=True,
        )
        out = self.output_dir / f"{photo_id}_print.png"
        img.save(out)
        return out

    def render_collage_color(
        self,
        photo_paths: Sequence[Path],
        photo_id: str,
    ) -> Path:
        """Save a color JPEG collage (for Cloudinary) matching the print grid."""
        if not self.output_dir:
            raise ValueError("output_dir is required")
        grid = self._build_grid_body(list(photo_paths), as_gray=False)
        out = self.output_dir.parent / "photos" / f"{photo_id}_grid.jpg"
        # Prefer photos_dir sibling — fall back next to prints
        photos_dir = self.output_dir.parent / "photos"
        photos_dir.mkdir(parents=True, exist_ok=True)
        out = photos_dir / f"{photo_id}_grid.jpg"
        grid.convert("RGB").save(out, quality=92)
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
        else:
            font_brand = self._font(22, bold=True)
            draw.text((x, 12), self.org_name, fill=0, font=font_brand)

        font_ts = self._font(14)
        ts_text = ts.strftime("%Y-%m-%d %H:%M:%S")
        tw = draw.textlength(ts_text, font=font_ts)
        draw.text((self.width - MARGIN - tw, (h - 18) // 2), ts_text, fill=0, font=font_ts)
        return img

    def _build_grid_body(
        self,
        photo_paths: Sequence[Path],
        as_gray: bool = True,
    ) -> Image.Image:
        cols = self.grid_cols
        rows = self.grid_rows
        slots = cols * rows

        inner_w = self.width - 2 * MARGIN
        cell_w = (inner_w - CELL_GAP * (cols - 1)) // cols
        cell_h = int(cell_w * self.portrait_aspect_h / self.portrait_aspect_w)

        grid_h = rows * cell_h + CELL_GAP * (rows - 1)
        mode = "L" if as_gray else "RGB"
        fill = 255 if as_gray else (255, 255, 255)
        frame = Image.new(mode, (self.width, grid_h + 2 * MARGIN), color=fill)

        paths = list(photo_paths)[:slots]
        while len(paths) < slots:
            paths.append(paths[-1] if paths else None)  # type: ignore[arg-type]

        for idx in range(slots):
            row, col = divmod(idx, cols)
            # Fill order: left→right, top→bottom (1 2 / 3 4)
            x = MARGIN + col * (cell_w + CELL_GAP)
            y = MARGIN + row * (cell_h + CELL_GAP)
            path = paths[idx]
            if path is None or not Path(path).exists():
                continue
            cell = self._portrait_cell(Path(path), cell_w, cell_h, as_gray=as_gray)
            frame.paste(cell, (x, y))

        return frame

    def _portrait_cell(
        self,
        photo_path: Path,
        cell_w: int,
        cell_h: int,
        as_gray: bool = True,
    ) -> Image.Image:
        photo = Image.open(photo_path).convert("RGB")
        # Auto-orient if EXIF says so, then center-crop to portrait cell
        photo = ImageOps.exif_transpose(photo)
        fitted = ImageOps.fit(photo, (cell_w, cell_h), method=Image.Resampling.LANCZOS)
        return ImageOps.grayscale(fitted) if as_gray else fitted

    def _build_footer(self, faculty: str, qr_url: str) -> Image.Image:
        qr = self._make_qr(qr_url, QR_SIZE)
        font = self._font(15)
        font_small = self._font(11)

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

        qr_x = self.width - MARGIN - QR_SIZE
        img.paste(qr, (qr_x, FOOTER_PAD))

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

    @staticmethod
    def _normalize_paths(photo_paths: Path | Sequence[Path]) -> list[Path]:
        if isinstance(photo_paths, Path):
            return [photo_paths]
        return [Path(p) for p in photo_paths]

    def _load_logo(self, max_h: int) -> Optional[Image.Image]:
        if not self.logo_path or not Path(self.logo_path).exists():
            logger.warning("logo.png not found at %s — using text brand", self.logo_path)
            return None
        logo = Image.open(self.logo_path).convert("RGBA")
        bg = Image.new("RGBA", logo.size, (255, 255, 255, 255))
        logo = Image.alpha_composite(bg, logo).convert("L")
        ratio = max_h / logo.height
        new_size = (max(1, int(logo.width * ratio)), max_h)
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
