(() => {
  const faculty = document.getElementById("faculty");
  const qrBase = document.getElementById("qrBase");
  const btn = document.getElementById("captureBtn");
  const statusBar = document.getElementById("statusBar");
  const preview = document.getElementById("preview");
  const resultMsg = document.getElementById("resultMsg");
  const photoPreview = document.getElementById("photoPreview");
  const printPreview = document.getElementById("printPreview");

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
        : `Camera: lỗi — ${data.camera?.error || "chưa kết nối"}`;
      const prn = data.printer?.connected
        ? `Printer: OK (${data.printer.backend})`
        : `Printer: chưa thấy (${data.printer?.backend || "?"})`;
      if (!btn.disabled) {
        setStatus(`${cam} · ${prn}`);
      }
    } catch {
      /* ignore polling errors */
    }
  }

  btn.addEventListener("click", async () => {
    if (!faculty.value) {
      setStatus("Hãy chọn Khoa / Ngành trước.", "err");
      faculty.focus();
      return;
    }
    if (!qrBase.value.includes("{id}")) {
      setStatus("URL base phải chứa {id}.", "err");
      qrBase.focus();
      return;
    }

    btn.disabled = true;
    setStatus("Đang chụp từ Sony A7S2 → render layout → gửi máy in…", "busy");

    const body = new FormData();
    body.append("faculty", faculty.value);
    body.append("qr_base_url", qrBase.value.trim());

    try {
      const res = await fetch("/api/capture-print", { method: "POST", body });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || res.statusText || "Lỗi không xác định");
      }

      setStatus(data.message, data.printed ? "ok" : "err");
      resultMsg.textContent = `#${data.photo_id} · ${data.captured_at} · QR: ${data.qr_url}`;
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
