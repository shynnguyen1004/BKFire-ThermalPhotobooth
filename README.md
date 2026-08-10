# BK FIRE Photobooth

macOS photobooth app for **Club Day**.

**Sony (USB / gphoto2) → 58mm thermal layout → POS58 + download QR**

If no Sony is connected, the app falls back to the MacBook camera automatically.

Every session captures **one portrait photo (3:4)**, places it in the center of the fixed print template, and prints.

---

## Requirements

| Device | Notes |
|--------|--------|
| Mac (Intel / Apple Silicon) | macOS 12+ |
| Sony (A7S II / gphoto2-compatible) | **Data** USB cable — not charge-only |
| Generic POS58 thermal printer | 58mm roll, printable width **384 px @ 203 DPI** |

### Sony body setup

1. **USB Connection** = **PC Remote** (or MTP if prompted)
2. **Image Quality** = Fine / Standard (JPEG) — avoid **RAW & JPEG** (the app keeps JPEG only and deletes `.ARW`)
3. Quit Imaging Edge / Wi‑Fi transfer on the Mac if it claims the USB device
4. Connect the USB cable to the Mac

Verify detection:

```bash
gphoto2 --auto-detect
```

---

## 1. System packages

```bash
brew install gphoto2 libgphoto2 libusb ffmpeg
```

### Free the camera from macOS (PTPCamera)

macOS often claims PTP cameras via `PTPCamera`. The app kills it before each shot. If you still get USB errors:

```bash
killall -9 PTPCamera
# Close Photos / Image Capture / Imaging Edge if they have the Sony open
gphoto2 --auto-detect
gphoto2 --capture-image-and-download
```

---

## 2. Python setup

```bash
cd "/path/to/BK Fire Photobooth"

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

Optional — install the `python-gphoto2` binding (faster than the CLI):

```bash
export LDFLAGS="-L/opt/homebrew/lib"
export CPPFLAGS="-I/opt/homebrew/include"
pip install python-gphoto2
```

Without the binding, the app still works by calling the `gphoto2` CLI.

---

## 3. Configuration

```bash
cp .env.example .env
```

### Cloudinary (required for online download QR)

1. Create an account at [cloudinary.com](https://cloudinary.com)
2. Put credentials in `.env`:

```env
CLOUDINARY_CLOUD_NAME=your_cloud
CLOUDINARY_API_KEY=xxxx
CLOUDINARY_API_SECRET=yyyy
CLOUDINARY_FOLDER=bk-fire-photobooth
```

After each **Capture & Print**, the JPEG is saved under `data/photos/` and uploaded to Cloudinary. The print QR always uses the short redirect URL from `QR_BASE_URL` — pasting a long Cloudinary `secure_url` into a ~62–122 px QR will not scan reliably.

```env
QR_BASE_URL=https://my-photobooth.app/photo/{id}
REGISTER_QR_URL=https://example.com/register
CAMERA_BACKEND=auto
PRINTER_BACKEND=cups
PRINTER_CUPS_NAME=POS58
```

| Variable | Meaning |
|----------|---------|
| `CAMERA_BACKEND` | `auto` (Sony → webcam fallback), `gphoto`, or `webcam` |
| `PRINTER_BACKEND` | `cups` (recommended on macOS), `usb`, or `file` (save raster only, no print) |
| `QR_BASE_URL` | Short download link; `{id}` is replaced with the photo id. Keep ≤ ~50 chars |
| `REGISTER_QR_URL` | Fixed “scan to register” QR on the right side of the strip |

### Print template

```
assets/print_template.png   # 384×955 px — logos + fixed text already baked in
```

The app only pastes:

- **One photo** in the center (full-bleed box ~381×420, cropped to 3:4)
- **Download QR** (left)
- **Register QR** (right)

To change the design, export a new PNG at exactly **384×955** and replace this file.

---

## 4. Run

```bash
source .venv/bin/activate
python main.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000)

1. Select **Faculty / Major**
2. Press **Capture & Print**

| Camera | Print result |
|--------|----------------|
| Sony USB | 1 portrait shot (3:4), centered on the template |
| MacBook (fallback) | Same — 1 portrait shot (3:4), centered on the template |

Pipeline: capture one JPEG → archive → upload Cloudinary → composite onto template + 2 QRs (photo dithered with Floyd–Steinberg; text stays sharp) → ESC/POS / CUPS print → guest scans QR and opens `/photo/{id}` to download.

---

## 5. Test layout without a camera

```bash
python scripts/demo_layout.py path/to/sample.jpg --faculty "Mechanical Engineering"
```

With `PRINTER_BACKEND=file`, the dithered strip is written to `data/prints/` only.

---

## Project layout

```
├── main.py
├── config/settings.py
├── app/
│   ├── domain/
│   ├── application/          # layout + photobooth orchestration
│   ├── infrastructure/
│   │   ├── camera/           # gphoto (Sony), webcam, auto fallback
│   │   ├── printer/          # POS58 ESC/POS / CUPS
│   │   └── storage/          # local files + Cloudinary
│   └── presentation/         # FastAPI + booth UI
├── assets/print_template.png
├── data/{temp,prints,photos}/
├── scripts/
└── requirements.txt
```

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Booth web UI |
| `GET` | `/api/status` | Camera + printer + Cloudinary status |
| `POST` | `/api/capture-print` | Form field: `faculty` |
| `GET` | `/photo/{id}` | Guest download page (QR target) |
| `GET` | `/photos/{id}.jpg` | Original JPEG |
| `GET` | `/prints/{id}_print.png` | Dithered print layout |

---

## Troubleshooting

**`Could not claim the USB device` / camera busy**  
→ `killall -9 PTPCamera`, then close Photos / Image Capture / Imaging Edge.

**Sony missing from `gphoto2 --auto-detect`**  
→ Set USB Connection to PC Remote, use a data cable (not charge-only), disable Wi‑Fi transfer on the body.

**Printer USB `Access denied`**  
→ Set `PRINTER_BACKEND=cups`, add the POS58 in **System Settings → Printers**, and match `PRINTER_CUPS_NAME`.

**Print looks gray / muddy**  
→ Photos are Floyd–Steinberg dithered for 1-bit thermal output. Raise printer density; avoid CUPS re-scaling (prefer the `usb` backend when it works).

**Sony also drops `.ARW` files**  
→ Image Quality is RAW & JPEG. Switch to Fine/Standard; the app still keeps JPEG only.

---

## License

Internal use — BK FIRE Club Day.
