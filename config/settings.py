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
    uploads_dir: Path = ROOT_DIR / "data" / "uploads"

    # QR / download base URL template — `{id}` is replaced with photo id
    qr_base_url: str = "https://my-photobooth.app/photo/{id}"

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

    # Web
    host: str = "0.0.0.0"
    port: int = 8000

    @field_validator("printer_vendor_id", "printer_product_id", mode="before")
    @classmethod
    def _hex_ids(cls, value: Union[int, str]) -> int:
        return _parse_hex_int(value)

    def ensure_dirs(self) -> None:
        for path in (self.temp_dir, self.prints_dir, self.uploads_dir):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
