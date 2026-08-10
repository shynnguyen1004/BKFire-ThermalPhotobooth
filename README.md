# BK FIRE Photobooth

Ứng dụng photobooth cho sự kiện **Club Day** trên macOS.

**Sony (USB / gphoto2) → Layout nhiệt 58mm → POS58 + QR tải ảnh**

Khi không có Sony, app tự chuyển sang camera MacBook (1 tấm).

---

## Yêu cầu

| Thiết bị | Ghi chú |
|----------|---------|
| Mac (Intel / Apple Silicon) | macOS 12+ |
| Sony (A7S II / tương thích gphoto2) | Cáp **data** USB, không dùng cáp chỉ sạc |
| Máy in nhiệt POS58 | Khổ 58mm, 384 px @ 203 DPI |

### Cài đặt nhanh trên thân máy Sony

1. **USB Connection** = **PC Remote** (hoặc MTP nếu máy hỏi)
2. **Image Quality** = Fine / Standard (JPEG) — tránh **RAW & JPEG** (app chỉ giữ JPEG, xoá `.ARW`)
3. Tắt Wi‑Fi / Imaging Edge trên Mac nếu đang chiếm USB
4. Cắm cáp USB → Mac

Kiểm tra nhận máy:

```bash
gphoto2 --auto-detect
```

---

## 1. Cài đặt hệ thống

```bash
brew install gphoto2 libgphoto2 libusb ffmpeg
```

### Giải phóng USB khỏi macOS (PTPCamera)

macOS thường chiếm camera qua `PTPCamera`. App tự kill trước mỗi lần chụp. Nếu vẫn lỗi:

```bash
killall -9 PTPCamera
# Đóng Photos / Image Capture / Imaging Edge đang mở với Sony
gphoto2 --auto-detect
gphoto2 --capture-image-and-download
```

---

## 2. Cài đặt Python

```bash
cd "/path/to/BK Fire Photobooth"

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

Tuỳ chọn — binding `python-gphoto2` (nhanh hơn CLI):

```bash
export LDFLAGS="-L/opt/homebrew/lib"
export CPPFLAGS="-I/opt/homebrew/include"
pip install python-gphoto2
```

---

## 3. Cấu hình

```bash
cp .env.example .env
```

### Cloudinary (bắt buộc cho QR online)

1. Tạo tài khoản tại [cloudinary.com](https://cloudinary.com)
2. Điền vào `.env`:

```env
CLOUDINARY_CLOUD_NAME=your_cloud
CLOUDINARY_API_KEY=xxxx
CLOUDINARY_API_SECRET=yyyy
CLOUDINARY_FOLDER=bk-fire-photobooth
```

QR trên phiếu in dùng link ngắn `QR_BASE_URL` (redirect tới ảnh). Không dán thẳng URL Cloudinary dài vào QR 62px — sẽ không quét được.

```env
QR_BASE_URL=https://my-photobooth.app/photo/{id}
REGISTER_QR_URL=https://example.com/register
CAMERA_BACKEND=auto
PRINTER_BACKEND=cups
PRINTER_CUPS_NAME=POS58
```

| Biến | Ý nghĩa |
|------|---------|
| `CAMERA_BACKEND` | `auto` (Sony → webcam), `gphoto`, hoặc `webcam` |
| `PRINTER_BACKEND` | `cups` (khuyến nghị trên macOS), `usb`, hoặc `file` (chỉ lưu ảnh, không in) |

### Template in

```
assets/print_template.png   # 384×842 px — logo + chữ cố định
```

App chỉ dán thêm: **ảnh** (ô 344×459, 3:4), **QR tải ảnh** (trái), **QR đăng ký** (phải). Đổi thiết kế: export PNG đúng 384×842 rồi thay file này.

---

## 4. Chạy

```bash
source .venv/bin/activate
python main.py
```

Mở [http://127.0.0.1:8000](http://127.0.0.1:8000)

1. Chọn **Khoa / Ngành**
2. Bấm **CHỤP & IN**

| Camera | Kết quả in |
|--------|------------|
| Sony USB | 4 tấm dọc 3:4 → grid 2×2 |
| MacBook (fallback) | 1 tấm 3:4 dọc → 1×1 |

Luồng: chụp JPEG → lưu `data/photos/` → upload Cloudinary → dán template + 2 QR (ảnh dither Floyd–Steinberg) → in → khách quét QR mở `/photo/{id}` để tải.

---

## 5. Test layout (không cần máy ảnh)

```bash
python scripts/demo_layout.py path/to/sample.jpg --faculty "Khoa Cơ khí"
```

Với `PRINTER_BACKEND=file`, chỉ lưu file vào `data/prints/`.

---

## Cấu trúc

```
├── main.py
├── config/settings.py
├── app/
│   ├── domain/
│   ├── application/          # layout + photobooth service
│   ├── infrastructure/
│   │   ├── camera/           # gphoto (Sony), webcam, auto
│   │   ├── printer/          # POS58 ESC/POS / CUPS
│   │   └── storage/          # file + Cloudinary
│   └── presentation/         # FastAPI + UI
├── assets/print_template.png
├── data/{temp,prints,photos}/
├── scripts/
└── requirements.txt
```

---

## API

| Method | Path | Mô tả |
|--------|------|--------|
| `GET` | `/` | Web UI booth |
| `GET` | `/api/status` | Trạng thái camera + printer |
| `POST` | `/api/capture-print` | Form: `faculty` |
| `GET` | `/photo/{id}` | Trang tải ảnh (QR) |
| `GET` | `/photos/{id}.jpg` | JPEG gốc |
| `GET` | `/prints/{id}_print.png` | Layout đã dither |

---

## Xử lý lỗi thường gặp

**`Could not claim the USB device` / camera busy**  
→ `killall -9 PTPCamera`, đóng Photos / Image Capture / Imaging Edge.

**Sony không hiện trong `gphoto2 --auto-detect`**  
→ USB Connection = PC Remote, cáp data (không phải charge-only), tắt Wi‑Fi transfer trên máy.

**Máy in USB `Access denied`**  
→ `PRINTER_BACKEND=cups`, thêm POS58 trong System Settings → Printers, tên khớp `PRINTER_CUPS_NAME`.

**Ảnh in xám / bẩn**  
→ Layout đã dither Floyd–Steinberg. Tăng mật độ in; tránh CUPS scale lại (ưu tiên backend `usb` nếu được).

**Sony xuất thêm file `.ARW`**  
→ Image Quality đang là RAW & JPEG. Đặt Fine/Standard; app vẫn chỉ giữ JPEG.

---

## Giấy phép

Nội bộ sự kiện BK FIRE Club Day.
