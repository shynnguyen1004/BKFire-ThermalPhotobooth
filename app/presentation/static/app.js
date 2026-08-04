(() => {
  const faculty = document.getElementById("faculty");
  const btn = document.getElementById("captureBtn");
  const statusBar = document.getElementById("statusBar");
  const preview = document.getElementById("preview");
  const resultMsg = document.getElementById("resultMsg");
  const photoPreview = document.getElementById("photoPreview");
  const printPreview = document.getElementById("printPreview");
  const frameGrid = document.getElementById("frameGrid");
  const cfg = window.BOOTH_CONFIG || { burstCount: 4, burstIntervalSec: 3 };

  function setStatus(text, kind) {
    statusBar.textContent = text;
    statusBar.classList.remove("is-busy", "is-ok", "is-err");
    if (kind) statusBar.classList.add(`is-${kind}`);
  }

  async function refreshDeviceStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      const cam = data.camera?.connected
        ? `Camera: ${data.camera.model || "OK"}`
        : data.camera?.detected
          ? `Camera: thấy ${data.camera.model || "Sony"} nhưng chưa claim USB — ${data.camera?.error || "rút/cắm lại"}`
          : `Camera: lỗi — ${data.camera?.error || "chưa kết nối"}`;
      const prn = data.printer?.connected
        ? `Printer: OK (${data.printer.backend})`
        : `Printer: chưa thấy (${data.printer?.backend || "?"})`;
      const cloud = data.cloudinary?.enabled
        ? `Cloudinary: OK (${data.cloudinary.folder || "root"})`
        : "Cloudinary: chưa cấu hình";
      const burst = data.burst
        ? `Burst: ${data.burst.count}×${data.burst.interval_sec}s (${data.burst.grid})`
        : "";
      if (!btn.disabled) {
        setStatus([cam, prn, cloud, burst].filter(Boolean).join(" · "));
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
    const waitHint = Math.round(
      cfg.burstCount * 8 + (cfg.burstCount - 1) * cfg.burstIntervalSec
    );
    setStatus(
      `Đang chụp ${cfg.burstCount} tấm dọc (cách ${cfg.burstIntervalSec}s) → grid 2×2 → Cloudinary → in… (~${waitHint}s)`,
      "busy"
    );

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
      resultMsg.textContent = `#${data.photo_id} · ${data.burst_count || cfg.burstCount} tấm · ${data.captured_at} · QR: ${qrLine}`;
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

  refreshDeviceStatus();
  setInterval(refreshDeviceStatus, 15000);
})();
