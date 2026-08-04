# BK FIRE Photobooth

Ứng dụng Python tự động hoá quy trình photobooth cho sự kiện **Club Day** trên macOS:

**Sony A7S2 (USB / gphoto2) → Layout nhiệt 58mm (Pillow + Floyd–Steinberg) → POS58 (ESC/POS) + QR tải ảnh**

---

## Yêu cầu phần cứng

| Thiết bị | Ghi chú |
|----------|---------|
| Mac (Intel / Apple Silicon) | macOS 12+ khuyến nghị |
| Sony A7S II (A7S2) | Cáp USB, bật USB Connection = **PC Remote** / MTP nếu được hỏi |
| Máy in nhiệt Generic POS58 | Khổ 58mm, vùng in **384 px @ 203 DPI**, USB |

---

## 1. Cài đặt hệ thống (Homebrew)

```bash
# Công cụ Homebrew (nếu chưa có): https://brew.sh
brew install gphoto2 libgphoto2 libusb

# Kiểm tra máy ảnh được nhận
gphoto2 --auto-detect
```

### Giải phóng máy ảnh khỏi PTPCamera (macOS)

macOS thường chiếm USB PTP qua tiến trình `PTPCamera` (Image Capture). Ứng dụng sẽ tự `killall PTPCamera` trước mỗi lần chụp. Nếu vẫn lỗi:

```bash
killall -9 PTPCamera
# Tắt tạm: System Settings → Printers & Scanners / Image Capture đang mở với A7S2
gphoto2 --auto-detect
gphoto2 --capture-image-and-download
```

Trên một số máy cần chạy photobooth bằng quyền đủ để truy cập USB (thử Terminal thường trước; nếu `python-escpos` báo access denied, dùng CUPS backend — xem bên dưới).

---

## 2. Cài đặt Python

```bash
cd "/path/to/BK Fire Photobooth"

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

Ứng dụng ưu tiên `python-gphoto2` nếu có; nếu không sẽ gọi CLI `gphoto2` (đã cài ở bước Homebrew). Binding Python là tuỳ chọn:

```bash
# Sau khi brew install gphoto2 libgphoto2
export LDFLAGS="-L/opt/homebrew/lib"
export CPPFLAGS="-I/opt/homebrew/include"
pip install python-gphoto2
```
---

## 3. Cấu hình

Sao chép file môi trường mẫu:

```bash
cp .env.example .env
```

### Cloudinary (bắt buộc cho QR online)

1. Tạo tài khoản tại [cloudinary.com](https://cloudinary.com)
2. Lấy **Cloud name / API Key / API Secret** từ Dashboard
3. Điền vào `.env`:

```env
CLOUDINARY_CLOUD_NAME=your_cloud
CLOUDINARY_API_KEY=xxxx
CLOUDINARY_API_SECRET=yyyy
CLOUDINARY_FOLDER=bk-fire-photobooth
```

Sau mỗi lần **CHỤP & IN**: JPEG lưu vào `data/photos/`, upload Cloudinary, QR trên phiếu in = `secure_url`.

> Sony đang xuất RAW+JPEG (file `.ARW`) dù bạn nghĩ chỉ chụp JPEG — thường do Image Quality = **RAW & JPEG**. App sẽ **chỉ giữ JPEG**, xoá RAW sau khi tải. Nên đặt Quality = Fine/Standard trên thân máy.

### Logo

Đặt file logo tổ chức vào:

```
assets/logo.png
```

Nếu chưa có, chạy script tạo logo placeholder:

```bash
python scripts/make_placeholder_logo.py
```

### Tìm USB ID máy in

```bash
system_profiler SPUSBDataType | grep -A 20 -i "print\|POS\|USB"
# hoặc
python -c "import usb.core,usb.util; 
import usb.core
for d in usb.core.find(find_all=True):
    print(hex(d.idVendor), hex(d.idProduct))"
```

---

## 4. Chạy ứng dụng

```bash
source .venv/bin/activate
python main.py
```

Mở trình duyệt: [http://127.0.0.1:8000](http://127.0.0.1:8000)

1. Chọn **Khoa / Ngành**
2. Kiểm / sửa **URL base QR**
3. Bấm **CHỤP & IN**

Luồng: capture JPEG → archive → render strip 384px → Floyd–Steinberg dither → ESC/POS print → guest mở `/photo/{id}` để tải ảnh.

---

## 5. Test layout không cần máy ảnh

```bash
python scripts/demo_layout.py path/to/sample.jpg --faculty "Khoa Cơ khí"
```

Với `PRINTER_BACKEND=file`, chỉ lưu file dither vào `data/prints/` (không gửi máy in).

---

## Cấu trúc (Clean Architecture)

```
├── main.py                      # Entry / uvicorn
├── config/settings.py           # Pydantic settings
├── app/
│   ├── domain/models.py         # CaptureResult, SessionResult, …
│   ├── application/
│   │   ├── layout_service.py    # Pillow layout + FLOYDSTEINBERG
│   │   └── photobooth_service.py
│   ├── infrastructure/
│   │   ├── camera/gphoto_camera.py   # gphoto2 + PTPCamera unbind
│   │   ├── printer/pos58_printer.py  # python-escpos / CUPS
│   │   └── storage/file_storage.py
│   └── presentation/
│       ├── api.py               # FastAPI routes
│       ├── templates/           # HTML
│       └── static/              # CSS / JS
├── assets/logo.png
├── data/{temp,prints,uploads}/
├── scripts/
├── requirements.txt
└── README.md
```

---

## API nhanh

| Method | Path | Mô tả |
|--------|------|--------|
| `GET` | `/` | Web UI booth |
| `GET` | `/api/status` | Trạng thái camera + printer |
| `POST` | `/api/capture-print` | Form: `faculty`, `qr_base_url` |
| `GET` | `/photo/{id}` | Trang tải ảnh cho khách (QR) |
| `GET` | `/photos/{id}.jpg` | File JPEG gốc |
| `GET` | `/prints/{id}_print.png` | Layout đã dither |

---

## Xử lý lỗi thường gặp

**`Could not claim the USB device` / camera busy**  
→ App đã gọi `release_macos_ptp_claim()`. Chạy thêm `killall -9 PTPCamera` và đóng Photos / Image Capture.

**Máy in USB `Access denied`**  
→ Đặt `PRINTER_BACKEND=cups`, thêm máy in POS58 trong **System Settings → Printers**, đặt tên khớp `PRINTER_CUPS_NAME`.

**Ảnh in quá xám / bẩn**  
→ Layout đã dither `Image.Dither.FLOYDSTEINBERG`. Kiểm tra máy in ở mật độ cao; tránh scale lại bằng phần mềm CUPS (dùng `usb` backend nếu được).

**Sony không hiện trong `gphoto2 --auto-detect`**  
→ Đổi mode USB trên thân máy, dùng cáp data (không phải charge-only), tắt Wi-Fi transfer trên camera.

---

## Giấy phép

Nội bộ sự kiện BK FIRE Club Day.
