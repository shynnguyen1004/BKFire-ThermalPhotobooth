"""FastAPI routes & app factory."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.application.layout_service import LayoutRenderer
from app.application.photobooth_service import PhotoboothService
from app.domain.models import PrintJobRequest
from app.infrastructure.camera.gphoto_camera import CameraError, GPhotoCamera
from app.infrastructure.printer.pos58_printer import POS58Printer
from app.infrastructure.storage.file_storage import FileStorage
from config.settings import Settings, settings

logger = logging.getLogger(__name__)

PRESENTATION_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(PRESENTATION_DIR / "templates"))


class CaptureBody(BaseModel):
    faculty: str = Field(..., min_length=1)
    qr_base_url: str = Field(..., min_length=8)


def build_service(cfg: Settings | None = None) -> PhotoboothService:
    cfg = cfg or settings
    cfg.ensure_dirs()
    camera = GPhotoCamera(
        temp_dir=cfg.temp_dir,
        model_hint=cfg.camera_model_hint,
        timeout_sec=cfg.capture_timeout_sec,
    )
    layout = LayoutRenderer(
        width=cfg.print_width_px,
        logo_path=cfg.logo_path,
        org_name=cfg.org_name,
        output_dir=cfg.prints_dir,
    )
    printer = POS58Printer(
        vendor_id=cfg.printer_vendor_id,
        product_id=cfg.printer_product_id,
        cups_name=cfg.printer_cups_name,
        backend=cfg.printer_backend,  # type: ignore[arg-type]
        dry_run_dir=cfg.prints_dir,
    )
    storage = FileStorage(uploads_dir=cfg.uploads_dir)
    return PhotoboothService(camera=camera, layout=layout, printer=printer, storage=storage)


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
                "qr_base_url": cfg.qr_base_url,
                "org_name": cfg.org_name,
            },
        )

    @app.get("/api/status")
    async def api_status() -> JSONResponse:
        return JSONResponse(booth.status())

    @app.post("/api/capture-print")
    async def api_capture_print(
        faculty: str = Form(...),
        qr_base_url: str = Form(...),
    ) -> JSONResponse:
        if not faculty.strip():
            raise HTTPException(status_code=400, detail="Chưa chọn Khoa / Ngành.")
        if "{id}" not in qr_base_url:
            raise HTTPException(
                status_code=400,
                detail="URL base phải chứa placeholder {id}, ví dụ https://my-photobooth.app/photo/{id}",
            )
        try:
            result = booth.capture_and_print(
                PrintJobRequest(faculty=faculty.strip(), qr_base_url=qr_base_url.strip())
            )
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
                "layout_url": f"/prints/{result.photo_id}_print.png",
                "photo_url": f"/photos/{result.photo_id}.jpg",
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
        """Guest download landing — matches QR URL pattern /photo/{id}."""
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
