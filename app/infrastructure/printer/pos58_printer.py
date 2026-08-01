"""POS58 thermal printer adapter (python-escpos)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Literal, Optional

from PIL import Image

logger = logging.getLogger(__name__)

Backend = Literal["usb", "cups", "file"]


class PrinterError(RuntimeError):
    """Raised when the thermal printer cannot complete a job."""


class POS58Printer:
    """
    Send a dithered 1-bit image to a Generic POS58 (58 mm / 384 px).

    Backends:
      - ``usb``  : python-escpos Usb (default Vendor 0x0416 / Product 0x5011)
      - ``cups`` : ``lp -d <name>`` via CUPS
      - ``file`` : dry-run — only confirm the raster exists (dev / no hardware)
    """

    def __init__(
        self,
        vendor_id: int = 0x0416,
        product_id: int = 0x5011,
        cups_name: str = "POS58",
        backend: Backend = "usb",
        dry_run_dir: Optional[Path] = None,
    ) -> None:
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.cups_name = cups_name
        self.backend: Backend = backend  # type: ignore[assignment]
        self.dry_run_dir = dry_run_dir

    def check_connection(self) -> dict:
        if self.backend == "file":
            return {"connected": True, "backend": "file", "note": "Dry-run mode"}
        if self.backend == "cups":
            result = subprocess.run(
                ["lpstat", "-p", self.cups_name],
                capture_output=True,
                text=True,
                check=False,
            )
            ok = result.returncode == 0
            return {
                "connected": ok,
                "backend": "cups",
                "printer": self.cups_name,
                "detail": (result.stdout or result.stderr).strip(),
            }
        # usb
        try:
            import usb.core

            dev = usb.core.find(idVendor=self.vendor_id, idProduct=self.product_id)
            return {
                "connected": dev is not None,
                "backend": "usb",
                "vendor_id": hex(self.vendor_id),
                "product_id": hex(self.product_id),
            }
        except Exception as exc:  # noqa: BLE001
            return {"connected": False, "backend": "usb", "error": str(exc)}

    def print_image(self, image: Image.Image | Path) -> None:
        """Print dithered image and feed/cut paper."""
        img = self._as_image(image)
        # Ensure 1-bit Floyd–Steinberg (idempotent if already dithered)
        if img.mode != "1":
            img = img.convert("L").convert("1", dither=Image.Dither.FLOYDSTEINBERG)

        # POS58 printable width
        if img.width != 384:
            ratio = 384 / img.width
            img = img.resize((384, max(1, int(img.height * ratio))), Image.Resampling.NEAREST)
            img = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)

        if self.backend == "file":
            self._print_file(img)
        elif self.backend == "cups":
            self._print_cups(img)
        else:
            self._print_usb(img)

    # ------------------------------------------------------------------

    def _print_usb(self, img: Image.Image) -> None:
        try:
            from escpos.printer import Usb
        except ImportError as exc:
            raise PrinterError("python-escpos chưa được cài.") from exc

        try:
            printer = Usb(self.vendor_id, self.product_id, profile="POS-5890")
        except Exception as exc:  # noqa: BLE001
            raise PrinterError(
                f"Không mở được POS58 USB ({hex(self.vendor_id)}:{hex(self.product_id)}): {exc}. "
                "Kiểm tra cáp, quyền USB, hoặc đặt PRINTER_BACKEND=cups."
            ) from exc

        try:
            # High-density raster bit image
            printer.set(align="center")
            printer.image(img, impl="bitImageRaster", high_density_vertical=True, high_density_horizontal=True)
            printer.text("\n")
            # Feed then partial cut (POS58 supports GS V)
            try:
                printer.cut(mode="PART")
            except Exception:  # noqa: BLE001
                printer.cut()
            logger.info("Printed via USB ESC/POS")
        except Exception as exc:  # noqa: BLE001
            raise PrinterError(f"Lỗi khi in ESC/POS: {exc}") from exc
        finally:
            try:
                printer.close()
            except Exception:  # noqa: BLE001
                pass

    def _print_cups(self, img: Image.Image) -> None:
        if not self.dry_run_dir:
            raise PrinterError("dry_run_dir required for CUPS temp file")
        tmp = self.dry_run_dir / "_cups_job.png"
        img.save(tmp)
        result = subprocess.run(
            ["lp", "-d", self.cups_name, "-o", "fit-to-page", str(tmp)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise PrinterError(f"CUPS lp failed: {result.stderr or result.stdout}")
        logger.info("Submitted CUPS job to %s: %s", self.cups_name, result.stdout.strip())

    def _print_file(self, img: Image.Image) -> None:
        if not self.dry_run_dir:
            raise PrinterError("dry_run_dir required for file backend")
        out = self.dry_run_dir / "_last_dry_run.png"
        img.save(out)
        logger.info("Dry-run print saved → %s", out)

    @staticmethod
    def _as_image(image: Image.Image | Path) -> Image.Image:
        if isinstance(image, Path):
            return Image.open(image)
        return image
