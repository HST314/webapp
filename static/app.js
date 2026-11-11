(() => {
  "use strict";

  const DEFAULTS = {
    scale: 0.025,
    dpi: 300,
    minArea: 500,
    minPieceArea: 200,
    closeTol: 2,
    colors: ["#CCCCFF", "#FF9933", "#00CCFF", "#99CCCC", "#CCFFCC"],
  };

  const EXTRA_COLORS = ["#FFCCCC", "#E5E5E0", "#FFE699", "#C9D6FF", "#D9F0D9", "#F2C7E3"];
  const MAX_COLORS = 12;
  const MAX_BYTES = 20 * 1024 * 1024;

  const form = document.getElementById("form");
  const drop = document.getElementById("drop");
  const fileInput = document.getElementById("file");
  const fileName = document.getElementById("file-name");
  const fileMeta = document.getElementById("file-meta");
  const scaleInput = document.getElementById("scale");
  const dpiInput = document.getElementById("dpi");
  const minAreaInput = document.getElementById("min-area");
  const minPieceAreaInput = document.getElementById("min-piece-area");
  const closeTolInput = document.getElementById("close-tol");
  const prefixInput = document.getElementById("prefix");
  const swatches = document.getElementById("swatches");
  const colorCount = document.getElementById("color-count");
  const addColorButton = document.getElementById("add-color");
  const resetColorsButton = document.getElementById("reset-colors");
  const resetParamsButton = document.getElementById("reset-params");
  const submitButton = document.getElementById("submit");
  const statusBox = document.getElementById("status");
  const result = document.getElementById("result");
  const resultCount = document.getElementById("result-count");
  const resultName = document.getElementById("result-name");
  const downloadLink = document.getElementById("download");

  const state = {
    colors: [...DEFAULTS.colors],
    file: null,
    prefixTouched: false,
    busy: false,
    objectUrl: null,
  };

  /* ---------- 通用 ---------- */

  function setStatus(message, kind) {
    statusBox.hidden = !message;
    statusBox.textContent = message;
    statusBox.dataset.state = kind || "info";
  }

  function setBusy(value) {
    state.busy = value;
    submitButton.disabled = value;
    submitButton.textContent = value ? "处理中…" : "开始填色并打包";
  }

  function formatSize(bytes) {
    if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  function stem(name) {
    return name.replace(/\.[^.]+$/, "");
  }

  function normalizeHex(raw) {
    let value = raw.trim().toUpperCase();
    if (!value.startsWith("#")) value = "#" + value;
    if (!/^#[0-9A-F]{3}$/.test(value) && !/^#[0-9A-F]{6}$/.test(value)) {
      return null;
    }
    if (value.length === 4) {
      value = "#" + [1, 2, 3].map((i) => value[i] + value[i]).join("");
    }
    return value;
  }

  function detailMessage(detail) {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => item.msg || String(item)).join("；");
    }
    return "请求参数有误。";
  }

  /* ---------- 色板 ---------- */

  function renderPalette() {
    swatches.innerHTML = "";
    colorCount.textContent = String(state.colors.length);
    addColorButton.disabled = state.colors.length >= MAX_COLORS;

    state.colors.forEach((color, index) => {
      const row = document.createElement("div");
      row.className = "swatch";

      const picker = document.createElement("input");
      picker.type = "color";
      picker.value = color;
      picker.setAttribute("aria-label", `第 ${index + 1} 个颜色`);

      const hex = document.createElement("input");
      hex.type = "text";
      hex.className = "swatch-hex";
      hex.value = color;
      hex.maxLength = 7;
      hex.setAttribute("aria-label", `第 ${index + 1} 个颜色的十六进制值`);

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "swatch-remove";
      remove.textContent = "×";
      remove.title = "移除这个颜色";
      remove.setAttribute("aria-label", `移除第 ${index + 1} 个颜色`);
      remove.disabled = state.colors.length <= 1;

      picker.addEventListener("input", () => {
        state.colors[index] = picker.value.toUpperCase();
        hex.value = state.colors[index];
      });

      hex.addEventListener("input", () => hex.classList.remove("is-invalid"));

      hex.addEventListener("change", () => {
        const normalized = normalizeHex(hex.value);
        if (normalized) {
          state.colors[index] = normalized;
          picker.value = normalized;
          hex.value = normalized;
        } else {
          hex.value = state.colors[index];
          hex.classList.add("is-invalid");
        }
      });

      remove.addEventListener("click", () => {
        if (state.colors.length <= 1) return;
        state.colors.splice(index, 1);
        renderPalette();
      });

      row.append(picker, hex, remove);
      swatches.append(row);
    });
  }

  addColorButton.addEventListener("click", () => {
    if (state.colors.length >= MAX_COLORS) return;
    const next =
      EXTRA_COLORS.find((color) => !state.colors.includes(color)) || "#FFFFFF";
    state.colors.push(next);
    renderPalette();
  });

  resetColorsButton.addEventListener("click", () => {
    state.colors = [...DEFAULTS.colors];
    renderPalette();
  });

  /* ---------- 参数 ---------- */

  function resetParams() {
    scaleInput.value = String(DEFAULTS.scale);
    dpiInput.value = String(DEFAULTS.dpi);
    minAreaInput.value = String(DEFAULTS.minArea);
    minPieceAreaInput.value = String(DEFAULTS.minPieceArea);
    closeTolInput.value = String(DEFAULTS.closeTol);
    state.prefixTouched = false;
    prefixInput.value = state.file ? stem(state.file.name) : "";
    state.colors = [...DEFAULTS.colors];
    renderPalette();
    setStatus("已恢复默认参数。", "info");
  }

  resetParamsButton.addEventListener("click", resetParams);

  prefixInput.addEventListener("input", () => {
    state.prefixTouched = true;
  });

  /* ---------- 文件选择 ---------- */

  function rejectFile(message) {
    state.file = null;
    fileInput.value = "";
    drop.classList.remove("has-file");
    fileName.textContent = "拖入 PLT 文件，或点此选择";
    fileMeta.hidden = true;
    fileMeta.textContent = "";
    setStatus(message, "error");
  }

  function acceptFile(file) {
    if (!/\.plt$/i.test(file.name)) {
      rejectFile("文件格式不对，需要 .plt 图纸。");
      return;
    }
    if (file.size > MAX_BYTES) {
      rejectFile("文件超过 20 MB 上限。");
      return;
    }
    state.file = file;
    drop.classList.add("has-file");
    fileName.textContent = file.name;
    fileMeta.textContent = formatSize(file.size);
    fileMeta.hidden = false;
    if (!state.prefixTouched) {
      prefixInput.value = stem(file.name);
    }
    setStatus("", "info");
  }

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    if (file) acceptFile(file);
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    drop.addEventListener(eventName, (event) => {
      event.preventDefault();
      drop.classList.add("is-over");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    drop.addEventListener(eventName, (event) => {
      event.preventDefault();
      drop.classList.remove("is-over");
    });
  });

  drop.addEventListener("drop", (event) => {
    const file = event.dataTransfer && event.dataTransfer.files[0];
    if (file) acceptFile(file);
  });

  // 防止文件被拖到页面其它位置时浏览器直接打开它
  ["dragover", "drop"].forEach((eventName) => {
    window.addEventListener(eventName, (event) => event.preventDefault());
  });

  /* ---------- 提交 ---------- */

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.busy) return;

    const file = state.file || (fileInput.files && fileInput.files[0]);
    if (!file) {
      setStatus("先选择一个 PLT 文件。", "error");
      return;
    }
    if (!/\.plt$/i.test(file.name)) {
      setStatus("只接受 .plt 文件。", "error");
      return;
    }
    if (file.size > MAX_BYTES) {
      setStatus("文件超过 20 MB 上限。", "error");
      return;
    }

    const scale = Number(scaleInput.value);
    const dpi = Number(dpiInput.value);
    const minArea = Number(minAreaInput.value);
    const minPieceArea = Number(minPieceAreaInput.value);
    const closeTol = Number(closeTolInput.value);

    if (![scale, dpi, minArea, minPieceArea, closeTol].every(Number.isFinite)) {
      setStatus("参数里出现了无效数字，请检查。", "error");
      return;
    }
    if (scale <= 0 || dpi < 36 || dpi > 2400 || minArea < 0 || minPieceArea < 0 || closeTol < 0) {
      setStatus("参数超出允许范围：换算比例须大于 0，DPI 为 36–2400，其余阈值不小于 0。", "error");
      return;
    }

    const formData = new FormData();
    formData.append("file", file, file.name);
    formData.append("scale", String(scale));
    formData.append("dpi", String(Math.round(dpi)));
    formData.append("min_area", String(minArea));
    formData.append("min_piece_area", String(minPieceArea));
    formData.append("close_tol", String(closeTol));
    formData.append("colors", JSON.stringify(state.colors));
    formData.append("prefix", prefixInput.value.trim());

    setBusy(true);
    result.hidden = true;
    setStatus("正在解析图纸并渲染…", "info");

    try {
      const response = await fetch("/api/convert", { method: "POST", body: formData });
      if (!response.ok) {
        const data = await response.json().catch(() => ({ detail: `服务返回 ${response.status}` }));
        throw new Error(detailMessage(data.detail));
      }

      const blob = await response.blob();
      const count = response.headers.get("X-Piece-Count") || "";
      let outName = "plt_fill.zip";
      const encodedName = response.headers.get("X-Output-Name");
      if (encodedName) {
        try {
          outName = decodeURIComponent(encodedName);
        } catch {
          outName = encodedName;
        }
      }

      if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
      state.objectUrl = URL.createObjectURL(blob);
      downloadLink.href = state.objectUrl;
      downloadLink.download = outName;

      resultCount.textContent = count || "?";
      resultName.textContent = `${outName} · ${formatSize(blob.size)}`;
      result.hidden = false;
      setStatus(`完成，已生成 ${count} 张 PNG。`, "done");

      downloadLink.click();

      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      result.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest" });
    } catch (error) {
      setStatus(error.message || "处理失败，请稍后重试。", "error");
    } finally {
      setBusy(false);
    }
  });

  renderPalette();
})();
