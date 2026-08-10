"""POS58 thermal printer adapter (python-escpos)."""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Literal, Optional

from PIL import Image

logger = logging.getLogger(__name__)

Backend = Literal["usb", "cups", "file"]

# Máy clone POS58 chỉ có buffer vài KB và firmware không flow-control tử tế:
# đẩy raster nhanh hơn tốc độ in là tràn buffer → rơi byte (in ra ký tự rác)
# rồi stall endpoint (Errno 32). Giải pháp: gửi từng dải nhỏ và nghỉ theo
# lượng mực (dải càng đậm đầu nhiệt in càng chậm).
BAND_ROWS = 48          # 48 dòng x 48 byte ≈ 2.3 KB mỗi dải
BAND_BASE_DELAY = 0.06  # giây — nghỉ tối thiểu giữa hai dải
BAND_INK_DELAY = 0.24   # giây — cộng thêm tỉ lệ thuận với mật độ điểm đen


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
            import usb.core
            from escpos.printer import Usb
        except ImportError as exc:
            raise PrinterError("python-escpos chưa được cài.") from exc

        class _UsbNoReset(Usb):
            """POS58 clone trên macOS: ``device.reset()`` trong ``Usb._configure_usb``
            làm handle libusb chết ngay sau đó (write dính Errno 5/32).
            Override để chỉ ``set_configuration``, bỏ ``reset``."""

            def _configure_usb(self) -> None:
                if not self.device:
                    return
                try:
                    self.device.set_configuration()
                except usb.core.USBError as exc:
                    logger.warning("USB set_configuration: %s", exc)
                # Job trước lỗi/ngắt giữa chừng có thể để endpoint kẹt HALT
                # → mọi write sau dính Errno 32. CLEAR_FEATURE gỡ stall mà
                # không re-enumerate thiết bị như reset().
                for ep in (self.out_ep, self.in_ep):
                    try:
                        self.device.clear_halt(ep)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("USB clear_halt(0x%02x): %s", ep, exc)

        try:
            # timeout 30s/lần ghi — máy kẹt buffer sẽ báo lỗi thay vì treo vô hạn
            printer = _UsbNoReset(
                self.vendor_id, self.product_id, timeout=30_000, profile="POS-5890"
            )
            printer.open()
        except Exception as exc:  # noqa: BLE001
            raise PrinterError(
                f"Không mở được POS58 USB ({hex(self.vendor_id)}:{hex(self.product_id)}): {exc}. "
                "Kiểm tra cáp, quyền USB, hoặc đặt PRINTER_BACKEND=cups."
            ) from exc

        try:
            printer.set(align="center")
            # Gửi raster theo dải nhỏ, tự điều tốc theo mật độ đen — xem chú
            # thích BAND_* ở đầu file.
            for top in range(0, img.height, BAND_ROWS):
                band = img.crop((0, top, img.width, min(top + BAND_ROWS, img.height)))
                printer.image(
                    band,
                    impl="bitImageRaster",
                    high_density_vertical=True,
                    high_density_horizontal=True,
                )
                black_ratio = band.histogram()[0] / (band.width * band.height)
                time.sleep(BAND_BASE_DELAY + BAND_INK_DELAY * black_ratio)
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
