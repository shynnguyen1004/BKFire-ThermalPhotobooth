"""Sony A7S2 capture via libgphoto2 (python-gphoto2) or gphoto2 CLI on macOS."""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.domain.models import CaptureResult, SessionResult

logger = logging.getLogger(__name__)


class CameraError(RuntimeError):
    """Raised when the camera cannot be used."""


class GPhotoCamera:
    """Capture JPEG stills from a USB-tethered Sony body (A7S II / A7S2)."""

    def __init__(self, temp_dir: Path, model_hint: str = "Sony", timeout_sec: int = 30) -> None:
        self.temp_dir = temp_dir
        self.model_hint = model_hint
        self.timeout_sec = timeout_sec
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_connection(self) -> dict:
        """Return camera status. Auto-frees PTPCamera if it holds the device."""
        self.release_macos_ptp_claim()
        if _has_python_gphoto2():
            return self._check_via_binding()
        return self._check_via_cli()

    def capture_photo(self, photo_id: Optional[str] = None) -> CaptureResult:
        """Trigger shutter, download JPEG to temp_dir, return CaptureResult."""
        self.release_macos_ptp_claim()
        photo_id = photo_id or SessionResult.new_id()
        dest = self.temp_dir / f"{photo_id}.jpg"

        if _has_python_gphoto2():
            try:
                return self._capture_via_binding(photo_id, dest)
            except CameraError:
                logger.warning("python-gphoto2 capture failed — retrying via CLI")
                self.release_macos_ptp_claim()
                time.sleep(0.5)

        return self._capture_via_cli(photo_id, dest)

    # ------------------------------------------------------------------
    # python-gphoto2 path
    # ------------------------------------------------------------------

    def _check_via_binding(self) -> dict:
        import gphoto2 as gp

        context = gp.Context()
        try:
            camera = gp.Camera()
            camera.init(context)
            summary = camera.get_summary(context).text
            abilities = camera.get_abilities()
            model = abilities.model
            camera.exit(context)
            connected = self.model_hint.lower() in model.lower() or "sony" in model.lower()
            return {
                "connected": True,
                "backend": "python-gphoto2",
                "model": model,
                "matches_hint": connected,
                "summary": summary.splitlines()[:8],
            }
        except gp.GPhoto2Error as exc:
            raise CameraError(
                f"Không kết nối được máy ảnh (gphoto2 error {exc.code}): {exc}. "
                "Rút/cắm lại USB, tắt Imaging Devices trên macOS, rồi thử lại."
            ) from exc

    def _capture_via_binding(self, photo_id: str, dest: Path) -> CaptureResult:
        import gphoto2 as gp

        context = gp.Context()
        camera = gp.Camera()
        try:
            camera.init(context)
            logger.info("Camera initialized (binding) — capturing %s", photo_id)
            self._prefer_jpeg(camera, context, gp)

            file_path = camera.capture(gp.GP_CAPTURE_IMAGE, context)
            camera_file = camera.file_get(
                file_path.folder,
                file_path.name,
                gp.GP_FILE_TYPE_NORMAL,
                context,
            )
            camera_file.save(str(dest))

            try:
                camera.file_delete(file_path.folder, file_path.name, context)
            except gp.GPhoto2Error:
                logger.debug("Could not delete capture from camera card")

            if not dest.exists() or dest.stat().st_size == 0:
                raise CameraError("File JPEG tải về trống hoặc không tồn tại.")

            return CaptureResult(
                photo_id=photo_id,
                local_path=dest,
                captured_at=datetime.now(),
            )
        except gp.GPhoto2Error as exc:
            if exc.code in (gp.GP_ERROR_IO, gp.GP_ERROR_MODEL_NOT_FOUND, -53, -60):
                self.release_macos_ptp_claim()
                time.sleep(0.8)
            raise CameraError(f"Capture thất bại (gphoto2 {exc.code}): {exc}") from exc
        finally:
            try:
                camera.exit(context)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # gphoto2 CLI fallback (brew install gphoto2)
    # ------------------------------------------------------------------

    def _check_via_cli(self) -> dict:
        gphoto2_bin = _require_gphoto2_cli()
        result = subprocess.run(
            [gphoto2_bin, "--auto-detect"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        output = (result.stdout or "") + (result.stderr or "")
        lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
        # Skip header lines like "Model", "---------"
        devices = [
            ln
            for ln in lines
            if not ln.lower().startswith("model") and not set(ln) <= {"-", " "}
        ]
        if not devices:
            raise CameraError(
                "gphoto2 --auto-detect không thấy máy ảnh. "
                "Cắm USB A7S2, chế độ PC Remote, rồi killall PTPCamera."
            )
        model = devices[0].split("usb:")[0].strip() if "usb:" in devices[0] else devices[0]
        return {
            "connected": True,
            "backend": "gphoto2-cli",
            "model": model,
            "matches_hint": self.model_hint.lower() in model.lower() or "sony" in model.lower(),
            "summary": devices[:5],
        }

    def _capture_via_cli(self, photo_id: str, dest: Path) -> CaptureResult:
        gphoto2_bin = _require_gphoto2_cli()
        work = self.temp_dir / f"_capture_{photo_id}"
        work.mkdir(parents=True, exist_ok=True)

        # Clear previous leftovers in work dir
        for old in work.glob("*"):
            old.unlink(missing_ok=True)

        cmd = [
            gphoto2_bin,
            "--capture-image-and-download",
            "--filename",
            str(work / "%f.%C"),
            "--force-overwrite",
        ]
        logger.info("Capturing via CLI: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=self.timeout_sec,
            cwd=str(work),
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            if "Could not claim" in err or "PTP" in err or "busy" in err.lower():
                self.release_macos_ptp_claim()
            raise CameraError(f"gphoto2 CLI capture thất bại: {err}")

        # Prefer JPEG over RAW
        downloaded = sorted(work.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        jpeg = next((p for p in downloaded if p.suffix.lower() in {".jpg", ".jpeg"}), None)
        if jpeg is None and downloaded:
            # Convert RAW is out of scope — require JPEG on camera
            raise CameraError(
                f"Máy trả về {downloaded[0].suffix} thay vì JPEG. "
                "Đặt Image Quality = JPEG / Fine trên A7S2."
            )
        if jpeg is None:
            raise CameraError("gphoto2 không tải được file ảnh về.")

        shutil.move(str(jpeg), str(dest))
        # Cleanup extras (e.g. .ARW alongside)
        for leftover in work.glob("*"):
            leftover.unlink(missing_ok=True)
        try:
            work.rmdir()
        except OSError:
            pass

        return CaptureResult(
            photo_id=photo_id,
            local_path=dest,
            captured_at=datetime.now(),
        )

    # ------------------------------------------------------------------
    # macOS PTP / Camera daemon handling
    # ------------------------------------------------------------------

    @staticmethod
    def release_macos_ptp_claim() -> None:
        """
        macOS auto-launches `PTPCamera` (Image Capture) which exclusives the USB
        PTP endpoint. Kill it so libgphoto2 can claim the Sony body.
        """
        for pattern in ("PTPCamera", "ptpcamera"):
            subprocess.run(
                ["killall", "-9", pattern],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        subprocess.run(
            ["pkill", "-9", "-f", "PTPCamera"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        gphoto2_bin = _which("gphoto2")
        if gphoto2_bin:
            subprocess.run(
                [gphoto2_bin, "--auto-detect"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )

        time.sleep(0.4)
        logger.debug("Released macOS PTPCamera claim (if any)")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _prefer_jpeg(camera, context, gp) -> None:
        """Try to switch capture target / image quality to JPEG when supported."""
        try:
            config = camera.get_config(context)
            for name in ("imagequality", "capturetarget"):
                try:
                    child = gp.check_result(gp.gp_widget_get_child_by_name(config, name))
                except gp.GPhoto2Error:
                    continue
                if name == "imagequality":
                    for choice in ("Standard", "Fine", "JPEG", "Extra Fine"):
                        try:
                            child.set_value(choice)
                            camera.set_config(config, context)
                            break
                        except gp.GPhoto2Error:
                            continue
                elif name == "capturetarget":
                    for choice in ("Memory card", "Card", "SDRAM", "Internal RAM"):
                        try:
                            child.set_value(choice)
                            camera.set_config(config, context)
                            break
                        except gp.GPhoto2Error:
                            continue
        except gp.GPhoto2Error as exc:
            logger.debug("Could not tune camera config: %s", exc)


def _which(binary: str) -> Optional[str]:
    from shutil import which

    return which(binary)


def _has_python_gphoto2() -> bool:
    try:
        import gphoto2  # noqa: F401

        return True
    except ImportError:
        return False


def _require_gphoto2_cli() -> str:
    path = _which("gphoto2")
    if not path:
        raise CameraError(
            "Chưa có gphoto2. Cài: brew install gphoto2 libgphoto2 "
            "rồi (tuỳ chọn) pip install python-gphoto2"
        )
    return path
