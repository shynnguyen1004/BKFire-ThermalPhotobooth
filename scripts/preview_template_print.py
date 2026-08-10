#!/usr/bin/env python3
"""Render sample print strips through the real LayoutRenderer.

Usage:
    python scripts/preview_template_print.py [photo1 photo2 ...] [--print single|grid]

Defaults to the sample portrait in "test layout print/". Previews land in
"test layout print/_preview/". With ``--print`` the chosen strip is also sent
to the printer configured in .env.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.application.layout_service import LayoutRenderer  # noqa: E402
from app.infrastructure.printer.pos58_printer import POS58Printer  # noqa: E402
from config.settings import settings  # noqa: E402

VARIANTS = {"single": (1, 1), "grid": (2, 2)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photos", nargs="*", type=Path, help="Sample photo(s)")
    parser.add_argument(
        "--print", dest="print_variant", choices=sorted(VARIANTS), default=None,
        help="Send this strip to the configured printer",
    )
    args = parser.parse_args()

    photos = args.photos or [ROOT / "test layout print" / "portrait.jpg"]
    for photo in photos:
        if not photo.exists():
            raise SystemExit(f"File not found: {photo}")

    out_dir = ROOT / "test layout print" / "_preview"
    out_dir.mkdir(exist_ok=True)

    qr_url = settings.qr_base_url.replace("{id}", "a1b2c3d4e5f6")
    print(f"QR download : {qr_url}")
    print(f"QR register : {settings.register_qr_url}")

    strips = {}
    for tag, (cols, rows) in VARIANTS.items():
        renderer = LayoutRenderer(
            template_path=settings.print_template_path,
            register_qr_url=settings.register_qr_url,
            grid_cols=cols,
            grid_rows=rows,
        )
        frames = (photos * (cols * rows))[: cols * rows]
        strips[tag] = renderer.render(frames, qr_url=qr_url, save=False)
        out = out_dir / f"pipeline_{tag}_{cols}x{rows}.png"
        strips[tag].save(out)
        print(f"{tag:7s} → {out}")

    if args.print_variant:
        printer = POS58Printer(
            vendor_id=settings.printer_vendor_id,
            product_id=settings.printer_product_id,
            cups_name=settings.printer_cups_name,
            backend=settings.printer_backend,  # type: ignore[arg-type]
            dry_run_dir=settings.prints_dir,
        )
        printer.print_image(strips[args.print_variant])
        print(f"printed {args.print_variant} via {settings.printer_backend}")


if __name__ == "__main__":
    main()
