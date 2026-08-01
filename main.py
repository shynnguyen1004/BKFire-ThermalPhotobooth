#!/usr/bin/env python3
"""BK FIRE Photobooth — entry point."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path when launched as `python main.py`
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn

from config.settings import settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    settings.ensure_dirs()
    uvicorn.run(
        "app.presentation.api:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
