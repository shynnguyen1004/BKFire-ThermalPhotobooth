(() => {
  const faculty = document.getElementById("faculty");
  const btn = document.getElementById("captureBtn");
  const captureHint = document.getElementById("captureHint");
  const statusBar = document.getElementById("statusBar");
  const preview = document.getElementById("preview");
  const resultMsg = document.getElementById("resultMsg");
  const photoPreview = document.getElementById("photoPreview");
  const printPreview = document.getElementById("printPreview");
  const frameGrid = document.getElementById("frameGrid");
  const cfg = window.BOOTH_CONFIG || { burstCount: 1, burstIntervalSec: 0 };

  let liveBurst = {
    count: cfg.burstCount,
    intervalSec: cfg.burstIntervalSec,
    aspect: "3:4",
    source: "gphoto",
  };

  function setStatus(text, kind) {
    statusBar.textContent = text;
    statusBar.classList.remove("is-busy", "is-ok", "is-err");
    if (kind) statusBar.classList.add(`is-${kind}`);
  }

  function updateCaptureHint() {
    if (!captureHint) return;
    const aspect = liveBurst.aspect || "3:4";
    if (liveBurst.source === "webcam") {
      captureHint.textContent = `MacBook cam · 1 tấm · ${aspect} dọc · in giữa phiếu`;
    } else {
      captureHint.textContent = `1 tấm dọc · ${aspect} · in giữa phiếu`;
    }
  }

  async function refreshDeviceStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      if (data.burst) {
        liveBurst = {
          count: data.burst.count ?? liveBurst.count,
          intervalSec: data.burst.interval_sec ?? liveBurst.intervalSec,
          aspect: data.burst.aspect || liveBurst.aspect,
          source: data.burst.source || liveBurst.source,
        };
        updateCaptureHint();
      }

      const camConnected = data.camera?.connected;
      const camSource = data.camera?.source || data.burst?.source;
      let cam;
      if (camConnected && camSource === "webcam") {
        cam = `Camera: MacBook (${data.camera?.aspect || liveBurst.aspect} dọc)`;
      } else if (camConnected) {
        cam = `Camera: ${data.camera.model || "OK"}`;
      } else if (data.camera?.detected) {
        cam = `Camera: thấy ${data.camera.model || "Sony"} nhưng chưa claim USB — ${data.camera?.error || "rút/cắm lại"}`;
      } else {
        cam = `Camera: lỗi — ${data.camera?.error || "chưa kết nối"}`;
      }

      const prn = data.printer?.connected
        ? `Printer: OK (${data.printer.backend}${data.printer.printer ? " · " + data.printer.printer : ""})`
        : `Printer: chưa thấy (${data.printer?.backend || "?"})`;
      const cloud = data.cloudinary?.enabled
        ? `Cloudinary: OK (${data.cloudinary.folder || "root"})`
        : "Cloudinary: chưa cấu hình";
      const mode = data.burst
        ? `Mode: 1 tấm · ${data.burst.aspect}`
        : "";
      if (!btn.disabled) {
        setStatus([cam, prn, cloud, mode].filter(Boolean).join(" · "));
      }
    } catch {
      /* ignore */
    }
  }

  function renderFrames(urls) {
    frameGrid.innerHTML = "";
    (urls || []).forEach((url, i) => {
      const fig = document.createElement("figure");
      const cap = document.createElement("figcaption");
      cap.textContent = `Tấm ${i + 1}`;
      const img = document.createElement("img");
      img.src = `${url}?t=${Date.now()}`;
      img.alt = `Frame ${i + 1}`;
      fig.append(cap, img);
      frameGrid.appendChild(fig);
    });
  }

  btn.addEventListener("click", async () => {
    if (!faculty.value) {
      setStatus("Hãy chọn Khoa / Ngành trước.", "err");
      faculty.focus();
      return;
    }

    btn.disabled = true;
    const modeHint =
      liveBurst.source === "webcam"
        ? "MacBook cam · 1 tấm → Cloudinary → in…"
        : "Đang chụp 1 tấm → Cloudinary → in… (~8s)";
    setStatus(modeHint, "busy");

    const body = new FormData();
    body.append("faculty", faculty.value);

    try {
      const res = await fetch("/api/capture-print", { method: "POST", body });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || res.statusText || "Lỗi không xác định");
      }

      setStatus(data.message, data.printed ? "ok" : "err");
      const qrLine = data.cloudinary_url || data.qr_url;
      resultMsg.textContent = `#${data.photo_id} · 1 tấm · ${data.captured_at} · QR: ${qrLine}`;
      renderFrames(data.frame_urls);
      const bust = `?t=${Date.now()}`;
      photoPreview.src = data.photo_url + bust;
      printPreview.src = data.layout_url + bust;
      preview.hidden = false;
    } catch (err) {
      setStatus(String(err.message || err), "err");
    } finally {
      btn.disabled = false;
      refreshDeviceStatus();
    }
  });

  updateCaptureHint();
  refreshDeviceStatus();
  setInterval(refreshDeviceStatus, 15000);
})();
