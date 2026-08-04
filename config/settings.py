"""Application settings — loaded from environment / defaults."""

from __future__ import annotations

from pathlib import Path
from typing import List, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


def _parse_hex_int(value: Union[int, str]) -> int:
    if isinstance(value, int):
        return value
    text = str(value).strip().lower()
    return int(text, 16) if text.startswith("0x") else int(text)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Branding
    org_name: str = "BK FIRE"
    logo_path: Path = ROOT_DIR / "assets" / "logo.png"

    # Print layout (POS58: 384 px @ 203 DPI)
    print_width_px: int = 384
    print_dpi: int = 203

    # Paths
    temp_dir: Path = ROOT_DIR / "data" / "temp"
    prints_dir: Path = ROOT_DIR / "data" / "prints"
    photos_dir: Path = ROOT_DIR / "data" / "photos"
    # legacy alias — same as photos_dir
    uploads_dir: Path = ROOT_DIR / "data" / "photos"

    # QR fallback when Cloudinary is disabled — `{id}` replaced with photo id
    qr_base_url: str = "https://my-photobooth.app/photo/{id}"

    # Cloudinary (QR uses secure_url after upload)
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    cloudinary_folder: str = "bk-fire-photobooth"

    # Faculties / majors shown in the UI dropdown
    faculties: List[str] = Field(
        default_factory=lambda: [
            "Khoa Khoa học và Kỹ thuật Máy tính",
            "Khoa Điện - Điện tử",
            "Khoa Cơ khí",
            "Khoa Xây dựng",
            "Khoa Hóa học & Kỹ thuật Hóa học",
            "Khoa Kỹ thuật Giao thông",
            "Khoa Quản lý Công nghiệp",
            "Khoa Khoa học Ứng dụng",
            "Khoa Môi trường & Tài nguyên",
            "Khoa Kỹ thuật Địa chất & Dầu khí",
            "Khác / Club Day Guest",
        ]
    )

    # POS58 USB IDs — Generic POS58 often uses 0x0416:0x5011
    printer_vendor_id: int = 0x0416
    printer_product_id: int = 0x5011
    # Optional CUPS printer name (used when USB direct fails)
    printer_cups_name: str = "POS58"
    # "usb" | "cups" | "file" (file = save raster only, for dry-run)
    printer_backend: str = "usb"

    # Camera
    camera_model_hint: str = "Sony"
    capture_timeout_sec: int = 30

    # Burst session — 4 portrait shots, then 2×2 grid print
    burst_count: int = 4
    burst_interval_sec: float = 3.0
    grid_cols: int = 2
    grid_rows: int = 2
    # Portrait cell aspect (width:height) e.g. 3:4
    portrait_aspect_w: int = 3
    portrait_aspect_h: int = 4

    # Web
    host: str = "0.0.0.0"
    port: int = 8000

    @field_validator("printer_vendor_id", "printer_product_id", mode="before")
    @classmethod
    def _hex_ids(cls, value: Union[int, str]) -> int:
        return _parse_hex_int(value)

    def ensure_dirs(self) -> None:
        for path in (self.temp_dir, self.prints_dir, self.photos_dir, self.uploads_dir):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def cloudinary_enabled(self) -> bool:
        return bool(
            self.cloudinary_cloud_name
            and self.cloudinary_api_key
            and self.cloudinary_api_secret
        )


settings = Settings()
settings.ensure_dirs()
