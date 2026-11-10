// Client-side compression of attendance certificates (jpg/png/pdf).
// Flow: pick file -> reject >25 MB or unsupported types -> if already <= 100 KB keep as is
// -> otherwise draw the image (or up to 3 PDF pages via lazily loaded pdf.js) onto a white canvas
// -> encode to WebP (JPEG fallback), lowering quality, then dimensions, until it fits 100 KB
// -> put the result back into the <input type=file>. The server only validates cheaply.
export const LIMIT_BYTES = 102400;

const MAX_INPUT_BYTES = 25 * 1024 * 1024;
const MAX_SIDE = 1600;
const PDF_WIDTH = 1000;
const PDF_MAX_PAGES = 3;
const PDF_GAP = 16;
const QUALITIES = [0.85, 0.75, 0.65, 0.55, 0.45];
const MIN_SIDE = 600;

let pdfjsPromise = null;

// Marks a failure to load pdf.js itself (as opposed to reading a broken file).
class LoaderError extends Error {
  constructor(cause) { super("pdf.js load failed", { cause }); }
}

function newCanvas(w, h) {
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(w));
  canvas.height = Math.max(1, Math.round(h));
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  return { canvas, ctx };
}

function detectKind(file) {
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  if (file.type === "application/pdf" || ext === "pdf") return "pdf";
  if (["image/jpeg", "image/png"].includes(file.type) || ["jpg", "jpeg", "png"].includes(ext)) return "image";
  return null;
}

async function imageToCanvas(file) {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  try {
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const { canvas, ctx } = newCanvas(bitmap.width * scale, bitmap.height * scale);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return canvas;
  } finally {
    bitmap.close();
  }
}

function loadPdfjs(src, workerSrc) {
  // import() resolves relative URLs against this module, so make them absolute against the page.
  const abs = (u) => new URL(u, document.baseURI).href;
  if (!src || !workerSrc) throw new LoaderError(new Error("pdf.js URLs are missing"));
  if (!pdfjsPromise) {
    pdfjsPromise = import(abs(src)).then((lib) => {
      lib.GlobalWorkerOptions.workerSrc = abs(workerSrc);
      return lib;
    }).catch((err) => { throw new LoaderError(err); });
    pdfjsPromise.catch(() => { pdfjsPromise = null; });
  }
  return pdfjsPromise;
}

async function pdfToCanvas(file, { pdfjsSrc, pdfjsWorker } = {}) {
  const lib = await loadPdfjs(pdfjsSrc, pdfjsWorker);
  const pdf = await lib.getDocument({ data: await file.arrayBuffer() }).promise;
  try {
    const count = Math.min(PDF_MAX_PAGES, pdf.numPages);
    const rendered = [];
    for (let n = 1; n <= count; n++) {
      const page = await pdf.getPage(n);
      const base = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: PDF_WIDTH / base.width });
      const { canvas, ctx } = newCanvas(viewport.width, viewport.height);
      await page.render({ canvasContext: ctx, viewport }).promise;
      page.cleanup();
      rendered.push(canvas);
    }
    const height = rendered.reduce((s, c) => s + c.height, 0) + PDF_GAP * (count - 1);
    const { canvas, ctx } = newCanvas(PDF_WIDTH, height);
    ctx.fillStyle = "#dddddd";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    let y = 0;
    for (const c of rendered) {
      ctx.drawImage(c, 0, y);
      y += c.height + PDF_GAP;
      c.width = c.height = 0;
    }
    const warning = pdf.numPages > PDF_MAX_PAGES ? `Збережено лише перші ${PDF_MAX_PAGES} сторінки з ${pdf.numPages}.` : null;
    return { canvas, pages: count, warning };
  } finally {
    await pdf.destroy();
  }
}

function toBlob(canvas, type, quality) {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

// Strategy: at each size, binary-search QUALITIES (sorted high -> low, size shrinks with quality)
// for the highest quality that fits, which takes at most 3 encodes instead of 5. If nothing fits,
// shrink by 0.8 and repeat; the last attempt is always made at exactly MIN_SIDE.
async function encodeUnderLimit(source) {
  let canvas = source;
  let type = "image/webp";
  const release = () => { if (canvas !== source) canvas.width = canvas.height = 0; };
  const encode = async (q) => {
    let blob = await toBlob(canvas, type, q);
    if (blob && type === "image/webp" && blob.type !== "image/webp") {
      type = "image/jpeg"; // browser lacks WebP encoding (older Safari)
      blob = await toBlob(canvas, type, q);
    }
    return blob;
  };
  for (;;) {
    let best = null;
    let lo = 0;
    let hi = QUALITIES.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const blob = await encode(QUALITIES[mid]);
      if (blob && blob.size <= LIMIT_BYTES) {
        best = blob; // fits: remember it and look for a higher quality
        hi = mid - 1;
      } else {
        lo = mid + 1;
      }
    }
    if (best) {
      release();
      return best;
    }
    const longest = Math.max(canvas.width, canvas.height);
    if (longest <= MIN_SIDE) {
      release();
      throw new Error("Не вдалося стиснути файл до 100 КБ. Спробуйте інше фото або скан.");
    }
    const scale = Math.max(longest * 0.8, MIN_SIDE) / longest;
    const next = newCanvas(canvas.width * scale, canvas.height * scale);
    next.ctx.imageSmoothingQuality = "high";
    next.ctx.drawImage(canvas, 0, 0, next.canvas.width, next.canvas.height);
    release();
    canvas = next.canvas;
  }
}

export async function compressCertificate(file, opts = {}) {
  const originalSize = file.size;
  if (originalSize > MAX_INPUT_BYTES) throw new Error("Файл завеликий (понад 25 МБ). Оберіть менший файл.");
  const kind = detectKind(file);
  if (!kind) throw new Error("Непідтримуваний тип файлу. Дозволено: JPG, PNG, PDF.");
  if (originalSize <= LIMIT_BYTES) return { file, originalSize, pages: null, warning: null };

  let canvas, pages = null, warning = null;
  try {
    if (kind === "pdf") ({ canvas, pages, warning } = await pdfToCanvas(file, opts));
    else canvas = await imageToCanvas(file);
  } catch (err) {
    if (err instanceof LoaderError) {
      throw new Error("Не вдалося завантажити модуль обробки PDF. Перевірте з'єднання та спробуйте ще раз.", { cause: err });
    }
    throw new Error("Не вдалося прочитати файл. Можливо, він пошкоджений або захищений паролем.", { cause: err });
  }

  try {
    const blob = await encodeUnderLimit(canvas);
    const ext = blob.type === "image/webp" ? "webp" : "jpg";
    const base = file.name.replace(/\.[^.]*$/, "") || "certificate";
    return { file: new File([blob], `${base}.${ext}`, { type: blob.type }), originalSize, pages, warning };
  } finally {
    canvas.width = canvas.height = 0;
  }
}

function formatSize(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${bytes} Б`;
}

export function attachCompressor(input) {
  if (input.dataset.compressAttached) return;
  input.dataset.compressAttached = "1";
  const status = document.createElement("p");
  status.className = "compress-status";
  status.setAttribute("aria-live", "polite");
  input.insertAdjacentElement("afterend", status);
  const show = (text, isError = false) => {
    status.textContent = text;
    status.classList.toggle("compress-status--error", isError);
  };
  let latest = 0;

  input.addEventListener("change", async () => {
    const file = input.files && input.files[0];
    const id = ++latest;
    const buttons = input.form ? [...input.form.querySelectorAll('[type="submit"], button:not([type])')] : [];
    if (!file) {
      buttons.forEach((b) => { b.disabled = false; }); // cancels any compression still running
      return show("");
    }
    buttons.forEach((b) => { b.disabled = true; });
    show("Стиснення файлу…");
    try {
      const result = await compressCertificate(file, {
        pdfjsSrc: input.dataset.pdfjsSrc,
        pdfjsWorker: input.dataset.pdfjsWorker,
      });
      if (id !== latest) return; // a newer selection superseded this one
      if (result.file === file) {
        show("Файл уже менший за 100 КБ, стиснення не потрібне.");
      } else {
        const dt = new DataTransfer();
        dt.items.add(result.file);
        input.files = dt.files;
        const msg = `Готово: ${formatSize(result.originalSize)} → ${formatSize(result.file.size)}`;
        show(result.warning ? `${msg}\n${result.warning}` : msg);
        status.style.whiteSpace = "pre-line";
      }
    } catch (err) {
      if (id !== latest) return;
      console.error(err);
      input.value = "";
      show(err.message || "Не вдалося обробити файл.", true);
    } finally {
      if (id === latest) buttons.forEach((b) => { b.disabled = false; });
    }
  });
}

function init() {
  document.querySelectorAll("input[type=file][data-compress-certificate]").forEach(attachCompressor);
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
}
