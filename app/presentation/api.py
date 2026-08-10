"""FastAPI routes & app factory."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.application.layout_service import LayoutRenderer
from app.application.photobooth_service import CaptureMode, PhotoboothService
from app.domain.models import PrintJobRequest
from app.infrastructure.camera.auto_camera import AutoCamera
from app.infrastructure.camera.gphoto_camera import CameraError, GPhotoCamera
from app.infrastructure.camera.webcam_camera import WebcamCamera
from app.infrastructure.printer.pos58_printer import POS58Printer
from app.infrastructure.storage.cloudinary_storage import CloudinaryStorage
from app.infrastructure.storage.file_storage import FileStorage
from config.settings import Settings, settings

logger = logging.getLogger(__name__)

PRESENTATION_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(PRESENTATION_DIR / "templates"))


def build_service(cfg: Settings | None = None) -> PhotoboothService:
    cfg = cfg or settings
    cfg.ensure_dirs()

    backend = (cfg.camera_backend or "auto").strip().lower()
    if backend not in ("auto", "gphoto", "webcam"):
        backend = "auto"

    gphoto = GPhotoCamera(
        temp_dir=cfg.temp_dir,
        model_hint=cfg.camera_model_hint,
        timeout_sec=cfg.capture_timeout_sec,
    )
    webcam = WebcamCamera(
        temp_dir=cfg.temp_dir,
        device_index=cfg.webcam_device_index,
        aspect_w=cfg.webcam_portrait_aspect_w,
        aspect_h=cfg.webcam_portrait_aspect_h,
    )
    camera = AutoCamera(
        gphoto=gphoto,
        webcam=webcam,
        backend=backend,  # type: ignore[arg-type]
    )

    layout = LayoutRenderer(
        template_path=cfg.print_template_path,
        register_qr_url=cfg.register_qr_url,
        output_dir=cfg.prints_dir,
        portrait_aspect_w=cfg.portrait_aspect_w,
        portrait_aspect_h=cfg.portrait_aspect_h,
    )
    printer = POS58Printer(
        vendor_id=cfg.printer_vendor_id,
        product_id=cfg.printer_product_id,
        cups_name=cfg.printer_cups_name,
        backend=cfg.printer_backend,  # type: ignore[arg-type]
        dry_run_dir=cfg.prints_dir,
    )
    storage = FileStorage(photos_dir=cfg.photos_dir)
    cloudinary = CloudinaryStorage(
        cloud_name=cfg.cloudinary_cloud_name,
        api_key=cfg.cloudinary_api_key,
        api_secret=cfg.cloudinary_api_secret,
        folder=cfg.cloudinary_folder,
    )
    return PhotoboothService(
        camera=camera,
        layout=layout,
        printer=printer,
        storage=storage,
        cloudinary=cloudinary,
        qr_base_url=cfg.qr_base_url,
        gphoto_mode=CaptureMode(
            burst_count=1,
            burst_interval_sec=0.0,
            portrait_aspect_w=cfg.portrait_aspect_w,
            portrait_aspect_h=cfg.portrait_aspect_h,
        ),
        webcam_mode=CaptureMode(
            burst_count=1,
            burst_interval_sec=0.0,
            portrait_aspect_w=cfg.webcam_portrait_aspect_w,
            portrait_aspect_h=cfg.webcam_portrait_aspect_h,
        ),
    )


def create_app(cfg: Settings | None = None, service: Optional[PhotoboothService] = None) -> FastAPI:
    cfg = cfg or settings
    booth = service or build_service(cfg)

    app = FastAPI(title="BK FIRE Photobooth", version="1.0.0")
    app.state.service = booth
    app.state.settings = cfg

    static_dir = PRESENTATION_DIR / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
            "index.html",
            {
                "request": request,
                "faculties": cfg.faculties,
                "org_name": cfg.org_name,
                "cloudinary_enabled": cfg.cloudinary_enabled,
                "cloudinary_folder": cfg.cloudinary_folder,
                "burst_count": cfg.burst_count,
                "burst_interval_sec": cfg.burst_interval_sec,
            },
        )

    @app.get("/api/status")
    async def api_status() -> JSONResponse:
        return JSONResponse(booth.status())

    @app.post("/api/capture-print")
    async def api_capture_print(
        faculty: str = Form(...),
    ) -> JSONResponse:
        if not faculty.strip():
            raise HTTPException(status_code=400, detail="Chưa chọn Khoa / Ngành.")
        try:
            result = booth.capture_and_print(PrintJobRequest(faculty=faculty.strip()))
        except CameraError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("capture-print failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return JSONResponse(
            {
                "ok": True,
                "photo_id": result.photo_id,
                "printed": result.printed,
                "qr_url": result.qr_url,
                "cloudinary_url": result.cloudinary_url,
                "layout_url": f"/prints/{result.photo_id}_print.png",
                "photo_url": f"/photos/{result.photo_id}.jpg",
                "frame_urls": [
                    f"/photos/{result.photo_id}_{i}.jpg"
                    for i in range(1, len(result.frame_paths) + 1)
                ],
                "burst_count": len(result.frame_paths),
                "message": result.message,
                "captured_at": result.captured_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    @app.get("/photos/{photo_id}.jpg")
    async def get_photo(photo_id: str) -> FileResponse:
        path = booth.storage.get_photo(photo_id)
        if path is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/prints/{filename}")
    async def get_print(filename: str) -> FileResponse:
        path = cfg.prints_dir / filename
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Print not found")
        return FileResponse(path, media_type="image/png")

    @app.get("/photo/{photo_id}")
    async def public_photo_page(photo_id: str, request: Request) -> HTMLResponse:
        path = booth.storage.get_photo(photo_id)
        if path is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        return TEMPLATES.TemplateResponse(
            "photo.html",
            {
                "request": request,
                "photo_id": photo_id,
                "photo_url": f"/photos/{photo_id}.jpg",
                "org_name": cfg.org_name,
            },
        )

    return app
