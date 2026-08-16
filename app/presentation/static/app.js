(() => {
  const btnCamera = document.getElementById("btnCamera");
  const btnWebcam = document.getElementById("btnWebcam");
  const btnReprint = document.getElementById("btnReprint");
  const reprintCopies = document.getElementById("reprintCopies");
  const btnCloseResult = document.getElementById("btnCloseResult");
  const hintCamera = document.getElementById("hintCamera");
  const hintWebcam = document.getElementById("hintWebcam");
  const hintReprint = document.getElementById("hintReprint");
  const statusBar = document.getElementById("statusBar");
  const viewport = document.getElementById("viewport");
  const liveVideo = document.getElementById("liveVideo");
  const viewportSubtitle = document.getElementById("viewportSubtitle");
  const btnEnableCam = document.getElementById("btnEnableCam");
  const btnPreviewToggle = document.getElementById("btnPreviewToggle");
  const previewToggleState = document.getElementById("previewToggleState");
  const liveBadge = document.getElementById("liveBadge");
  const liveBadgeText = document.getElementById("liveBadgeText");
  const resultDrawer = document.getElementById("resultDrawer");
  const resultMsg = document.getElementById("resultMsg");
  const photoPreview = document.getElementById("photoPreview");
  const printPreview = document.getElementById("printPreview");
  const frameGrid = document.getElementById("frameGrid");
  const clockTime = document.getElementById("clockTime");
  const clockDate = document.getElementById("clockDate");
  const resBadge = document.getElementById("resBadge");

  const dotCamera = document.getElementById("dotCamera");
  const dotWebcam = document.getElementById("dotWebcam");
  const dotPrinter = document.getElementById("dotPrinter");
  const dotCloud = document.getElementById("dotCloud");
  const dotLast = document.getElementById("dotLast");
  const valCamera = document.getElementById("valCamera");
  const valWebcam = document.getElementById("valWebcam");
  const valPrinter = document.getElementById("valPrinter");
  const valCloud = document.getElementById("valCloud");
  const valLast = document.getElementById("valLast");

  let busy = false;
  let lastPrint = null;
  let toastTimer = null;
  let liveStream = null;
  // Mặc định tắt — webcam luôn mở sẽ nóng máy.
  let previewWanted = false;
  let startingPreview = false;
  let cameras = {
    gphoto: { connected: false },
    webcam: { connected: false },
  };

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function tickClock() {
    const now = new Date();
    if (clockTime) {
      clockTime.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(
        now.getSeconds()
      )}`;
    }
    if (clockDate) {
      clockDate.textContent = `${pad(now.getDate())}.${pad(
        now.getMonth() + 1
      )}.${now.getFullYear()}`;
    }
  }

  function setDot(el, kind) {
    if (!el) return;
    el.classList.remove("is-ok", "is-warn", "is-err", "is-muted");
    el.classList.add(`is-${kind || "muted"}`);
  }

  function setLiveUi(isLive) {
    viewport?.classList.toggle("is-live", !!isLive);
    if (liveVideo) liveVideo.hidden = !isLive;
    if (btnEnableCam) btnEnableCam.hidden = !!isLive;
    liveBadge?.classList.toggle("is-off", !isLive);
    if (liveBadgeText) liveBadgeText.textContent = isLive ? "LIVE" : "OFF";
    if (btnPreviewToggle) {
      btnPreviewToggle.setAttribute("aria-pressed", previewWanted ? "true" : "false");
    }
    if (previewToggleState) {
      previewToggleState.textContent = previewWanted ? "ON" : "OFF";
    }
    if (!isLive && viewportSubtitle && !busy) {
      viewportSubtitle.textContent = previewWanted
        ? explainCameraBlock()
        : "Preview đang tắt — bấm để bật khi cần";
    }
    if (btnEnableCam && !isLive) {
      btnEnableCam.textContent = previewWanted ? "Cho phép Camera" : "Bật Preview Webcam";
    }
  }

  async function setPreviewWanted(on, { fromUserGesture = true } = {}) {
    previewWanted = !!on;
    setLiveUi(!!liveStream);
    if (previewWanted) {
      await startLivePreview({ fromUserGesture });
    } else {
      stopLivePreview();
      setLiveUi(false);
    }
  }

  function cameraApiAvailable() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  }

  function explainCameraBlock() {
    if (!window.isSecureContext) {
      return "Mở qua http://127.0.0.1:8000 (HTTPS/localhost) để dùng Camera";
    }
    if (!cameraApiAvailable()) {
      return "Trình duyệt hiện không mở được Camera API";
    }
    return "Bấm “Cho phép Camera” để hiện hộp thoại quyền";
  }

  function updateResBadge() {
    if (!resBadge || !liveVideo) return;
    const w = liveVideo.videoWidth;
    const h = liveVideo.videoHeight;
    if (!w || !h) {
      resBadge.textContent = "—";
      return;
    }
    const long = Math.max(w, h);
    resBadge.textContent = long >= 1800 ? "1080p" : long >= 1200 ? "720p" : `${w}×${h}`;
  }

  function stopLivePreview() {
    if (liveStream) {
      liveStream.getTracks().forEach((t) => t.stop());
      liveStream = null;
    }
    if (liveVideo) {
      liveVideo.srcObject = null;
    }
    setLiveUi(false);
    if (resBadge) resBadge.textContent = "—";
  }

  async function startLivePreview({ fromUserGesture = false } = {}) {
    if (!previewWanted || busy || startingPreview) return false;
    if (liveStream) return true;

    if (!cameraApiAvailable()) {
      if (viewportSubtitle) viewportSubtitle.textContent = explainCameraBlock();
      if (btnEnableCam) btnEnableCam.hidden = false;
      return false;
    }

    startingPreview = true;
    if (btnEnableCam) {
      btnEnableCam.disabled = true;
      btnEnableCam.textContent = "Đang xin quyền…";
    }
    if (viewportSubtitle) {
      viewportSubtitle.textContent = fromUserGesture
        ? "Đang yêu cầu quyền Camera…"
        : "Đang kết nối webcam…";
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: "user",
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
      });
      liveStream = stream;
      if (liveVideo) {
        liveVideo.srcObject = stream;
        await liveVideo.play().catch(() => {});
      }
      setLiveUi(true);
      updateResBadge();
      if (viewportSubtitle) viewportSubtitle.textContent = "Live preview";
      return true;
    } catch (err) {
      setLiveUi(false);
      let msg = "Không mở được webcam preview";
      if (err?.name === "NotAllowedError" || err?.name === "PermissionDeniedError") {
        msg = fromUserGesture
          ? "Bạn đã từ chối Camera — hãy bật lại trong thanh địa chỉ"
          : "Cần cho phép Camera — bấm nút bên dưới";
      } else if (err?.name === "NotFoundError" || err?.name === "DevicesNotFoundError") {
        msg = "Không tìm thấy webcam";
      } else if (err?.name === "NotReadableError" || err?.name === "TrackStartError") {
        msg = "Webcam đang bị app khác giữ — đóng Zoom/Meet rồi thử lại";
      } else if (!window.isSecureContext) {
        msg = explainCameraBlock();
      }
      if (viewportSubtitle) viewportSubtitle.textContent = msg;
      if (btnEnableCam) {
        btnEnableCam.hidden = false;
        btnEnableCam.textContent = "Cho phép Camera";
      }
      return false;
    } finally {
      startingPreview = false;
      if (btnEnableCam) btnEnableCam.disabled = false;
    }
  }

  async function withPreviewPaused(fn) {
    const resumeAfter = previewWanted;
    const wasLive = !!liveStream;
    previewWanted = false;
    stopLivePreview();
    // Give macOS/AVFoundation a moment to release the device for ffmpeg.
    await new Promise((r) => setTimeout(r, wasLive ? 350 : 0));
    try {
      return await fn();
    } finally {
      previewWanted = resumeAfter;
      setLiveUi(false);
      if (previewWanted) {
        await startLivePreview({ fromUserGesture: false });
      }
    }
  }

  function setStatus(text, kind) {
    if (!statusBar) return;
    statusBar.textContent = text || "";
    statusBar.classList.remove("is-busy", "is-ok", "is-err");
    if (kind) statusBar.classList.add(`is-${kind}`);
    statusBar.hidden = !text;

    if (viewportSubtitle && !liveStream && kind !== "ok") {
      viewportSubtitle.textContent = text || "Awaiting connection...";
    }
    if (viewport) {
      viewport.classList.toggle("is-busy", kind === "busy");
      viewport.classList.toggle("is-err", kind === "err");
    }

    clearTimeout(toastTimer);
    if (text && kind !== "busy") {
      toastTimer = setTimeout(() => {
        statusBar.hidden = true;
      }, 6000);
    }
  }

  function setBusy(isBusy) {
    busy = isBusy;
    updateButtons();
  }

  function updateButtons() {
    const camOk = !!cameras.gphoto?.connected;
    const webOk = !!cameras.webcam?.connected;
    const hasLast = !!(lastPrint && lastPrint.photo_id);

    if (btnCamera) btnCamera.disabled = busy || !camOk;
    if (btnWebcam) btnWebcam.disabled = busy || !webOk;
    if (btnReprint) btnReprint.disabled = busy || !hasLast;

    if (hintCamera) {
      hintCamera.textContent = camOk
        ? "Capture by Camera & Print"
        : cameras.gphoto?.error || "Camera disconnected";
    }
    if (hintWebcam) {
      hintWebcam.textContent = webOk
        ? "Capture by Webcam & Print"
        : cameras.webcam?.error || "Webcam unavailable";
    }
    if (hintReprint) {
      hintReprint.textContent = hasLast ? "Reprint" : "No previous print";
    }
  }

  function applyDeviceStatus(data) {
    const camOk = !!cameras.gphoto?.connected;
    const webOk = !!cameras.webcam?.connected;
    const prnOk = !!data.printer?.connected;
    const cloudOk = !!data.cloudinary?.enabled;
    const hasLast = !!lastPrint?.photo_id;

    setDot(dotCamera, camOk ? "ok" : "warn");
    setDot(dotWebcam, webOk ? "ok" : "warn");
    setDot(dotPrinter, prnOk ? "ok" : "warn");
    setDot(dotCloud, cloudOk ? "ok" : "warn");
    setDot(dotLast, hasLast ? "ok" : "muted");

    if (valCamera) {
      valCamera.textContent = camOk
        ? cameras.gphoto.model || "OK"
        : "chờ kết nối";
      valCamera.classList.toggle("is-warn", !camOk);
    }
    if (valWebcam) {
      valWebcam.textContent = webOk
        ? cameras.webcam.model || "OK"
        : "chưa sẵn sàng";
      valWebcam.classList.toggle("is-warn", !webOk);
    }
    if (valPrinter) {
      valPrinter.textContent = prnOk
        ? `OK (${data.printer.backend || "usb"})`
        : "chưa thấy";
      valPrinter.classList.toggle("is-warn", !prnOk);
    }
    if (valCloud) {
      valCloud.textContent = cloudOk ? "OK" : "chưa cấu hình";
      valCloud.classList.toggle("is-warn", !cloudOk);
    }
    if (valLast) {
      valLast.textContent = hasLast ? `#${lastPrint.photo_id}` : "—";
    }

    if (previewWanted && !liveStream && !busy) {
      startLivePreview({ fromUserGesture: false });
    }
  }

  async function refreshDeviceStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      if (data.cameras) {
        cameras = {
          gphoto: data.cameras.gphoto || { connected: false },
          webcam: data.cameras.webcam || { connected: false },
        };
      }
      if (data.last_print) lastPrint = data.last_print;
      updateButtons();
      applyDeviceStatus(data);
    } catch {
      /* ignore */
    }
  }

  function renderFrames(urls) {
    if (!frameGrid) return;
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

  function showResult(data) {
    const qrLine = data.cloudinary_url || data.qr_url;
    if (resultMsg) {
      resultMsg.textContent = `#${data.photo_id} · ${data.captured_at} · QR: ${qrLine}`;
    }
    renderFrames(data.frame_urls);
    const bust = `?t=${Date.now()}`;
    if (photoPreview) photoPreview.src = data.photo_url + bust;
    if (printPreview) printPreview.src = data.layout_url + bust;
    if (resultDrawer) resultDrawer.hidden = false;
    lastPrint = {
      photo_id: data.photo_id,
      layout_url: data.layout_url,
      photo_url: data.photo_url,
      captured_at: data.captured_at,
    };
    updateButtons();
  }

  function closeResult() {
    if (resultDrawer) resultDrawer.hidden = true;
  }

  function selectedDitherStyle() {
    const el = document.querySelector('input[name="ditherStyle"]:checked');
    return el?.value === "comic" ? "comic" : "floyd";
  }

  async function runCapture(source, busyLabel) {
    setBusy(true);
    setStatus(busyLabel, "busy");

    const body = new FormData();
    body.append("dither_style", selectedDitherStyle());
    body.append("source", source);

    const doRequest = async () => {
      const res = await fetch("/api/capture-print", { method: "POST", body });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || res.statusText || "Lỗi không xác định");
      }
      return data;
    };

    try {
      // Pause browser webcam so ffmpeg can capture the same device on macOS.
      const data =
        source === "webcam" ? await withPreviewPaused(doRequest) : await doRequest();
      setStatus(data.message, data.printed ? "ok" : "err");
      showResult(data);
    } catch (err) {
      setStatus(String(err.message || err), "err");
    } finally {
      setBusy(false);
      refreshDeviceStatus();
    }
  }

  function selectedCopies() {
    const n = Number.parseInt(String(reprintCopies?.value || "1"), 10);
    if (!Number.isFinite(n)) return 1;
    return Math.max(1, Math.min(20, n));
  }

  async function runReprint() {
    const copies = selectedCopies();
    if (reprintCopies) reprintCopies.value = String(copies);
    setBusy(true);
    setStatus(
      copies > 1 ? `Đang in lại ${copies} bản…` : "Đang in lại lần gần nhất…",
      "busy"
    );
    const body = new FormData();
    body.append("dither_style", selectedDitherStyle());
    body.append("copies", String(copies));
    try {
      const res = await fetch("/api/reprint-last", { method: "POST", body });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || res.statusText || "Lỗi không xác định");
      }
      setStatus(data.message, data.printed ? "ok" : "err");
      showResult(data);
    } catch (err) {
      setStatus(String(err.message || err), "err");
    } finally {
      setBusy(false);
      refreshDeviceStatus();
    }
  }

  btnCamera?.addEventListener("click", () =>
    runCapture("gphoto", "Đang chụp bằng máy ảnh → Cloudinary → in…")
  );
  btnWebcam?.addEventListener("click", () =>
    runCapture("webcam", "Đang chụp bằng webcam → Cloudinary → in…")
  );
  btnReprint?.addEventListener("click", runReprint);
  btnCloseResult?.addEventListener("click", closeResult);
  btnEnableCam?.addEventListener("click", () => {
    setPreviewWanted(true, { fromUserGesture: true });
  });
  btnPreviewToggle?.addEventListener("click", () => {
    setPreviewWanted(!previewWanted, { fromUserGesture: true });
  });
  liveVideo?.addEventListener("loadedmetadata", updateResBadge);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopLivePreview();
    } else if (previewWanted && !busy) {
      startLivePreview({ fromUserGesture: false });
    }
  });

  if (viewportSubtitle) {
    viewportSubtitle.textContent = "Preview đang tắt — bấm để bật khi cần";
  }
  setLiveUi(false);

  tickClock();
  setInterval(tickClock, 1000);
  updateButtons();
  refreshDeviceStatus();
  setInterval(refreshDeviceStatus, 8000);
})();
