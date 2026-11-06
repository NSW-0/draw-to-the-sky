// Draw to the Sky — phone page: take pictures, see / delete photos, delete all
const UPLOAD_LONG_SIDE = 1600;   // phone shrinks the photo before upload (faster on Wi-Fi)
const $ = (id) => document.getElementById(id);
const fileInput = $("file");
const sens = $("sens");
let token = null, reqSeq = 0, sending = false, doneTimer = null, pinRequired = false;

const MSG = {
  network: "The laptop can't be reached. Check this phone is on the same Wi-Fi, then try again.",
  badImage: "This photo can't be read. Take it again.",
};

// ------------------------------------------------------------------ helpers ----
function show(id) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("show", s.id === id));
  document.body.classList.toggle("dark", id !== "s-home");   // art is brightest on the home screen
  window.scrollTo(0, 0);
  if (id === "s-home") refreshCount();
}
function setError(id, msg) {
  const el = $(id);
  el.textContent = msg || "";
  el.classList.toggle("show", !!msg);
}
function busy(on) { $("busy").classList.toggle("show", on); }
function toast(msg) {
  const el = $("toast");
  el.textContent = msg; el.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.remove("show"), 2200);
}
function plural(n, one, many) { return n === 1 ? `1 ${one}` : `${n} ${many}`; }

async function post(url, body, type) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 30000);
  try {
    return await fetch(url, { method: "POST", body, headers: type ? { "Content-Type": type } : {}, signal: ctl.signal });
  } finally { clearTimeout(t); }
}

// remember the helper's slider setting between photos
const saved = localStorage.getItem("sensitivity");
fetch("/api/info").then((r) => r.json()).then((i) => {
  pinRequired = !!i.pin_required;
  if (saved === null) sens.value = i.default_sensitivity;
}).catch(() => {});
if (saved !== null) sens.value = saved;

// ----------------------------------------------------------- confirm sheet ----
function confirmSheet({ title, text, yes, no = "Keep", img }) {
  return new Promise((resolve) => {
    $("sheetTitle").textContent = title;
    $("sheetText").textContent = text;
    $("sheetYes").textContent = yes;
    $("sheetNo").textContent = no;
    $("sheetImg").hidden = !img;
    if (img) $("sheetImg").src = img;
    $("sheet").classList.add("show");
    const done = (v) => { $("sheet").classList.remove("show"); $("sheetYes").onclick = $("sheetNo").onclick = $("sheet").onclick = null; resolve(v); };
    $("sheetYes").onclick = () => done(true);
    $("sheetNo").onclick = () => done(false);
    $("sheet").onclick = (e) => { if (e.target === $("sheet")) done(false); };
  });
}

// --------------------------------------------------------- admin requests ----
async function adminFetch(url, method) {
  const send = () => fetch(url, { method, headers: { "X-Admin-Pin": localStorage.getItem("adminPin") || "" } });
  let r = await send();
  if (r.status === 403 && pinRequired) {
    const pin = window.prompt("Enter the delete PIN (set on the laptop):");
    if (!pin) return null;
    localStorage.setItem("adminPin", pin.trim());
    r = await send();
    if (r.status === 403) { localStorage.removeItem("adminPin"); toast("Wrong PIN"); return null; }
  }
  return r;
}

function refusedMessage(r) {
  if (r.status === 403) return pinRequired ? "Wrong PIN" : "The laptop said no. Restart the server on the laptop";
  return "Couldn't delete. Try again";
}

async function listDrawings() {
  const r = await fetch("/api/drawings", { cache: "no-store" });
  return await r.json();
}

async function refreshCount() {
  try { $("count").textContent = (await listDrawings()).length; } catch (e) {}
}
refreshCount();

// ------------------------------------------------------------ take picture ----
function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { resolve(img); setTimeout(() => URL.revokeObjectURL(url), 1000); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("decode")); };
    img.src = url;
  });
}

async function shrink(file) {
  const img = await loadImage(file);    // browsers apply the photo's rotation (EXIF) here
  const w = img.naturalWidth, h = img.naturalHeight;
  const s = Math.min(1, UPLOAD_LONG_SIDE / Math.max(w, h));
  const c = document.createElement("canvas");
  c.width = Math.round(w * s); c.height = Math.round(h * s);
  c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
  return await new Promise((res) => c.toBlob(res, "image/jpeg", 0.9));
}

function applyResult(j) {
  if (j.ok) {
    $("preview").src = j.preview;
    $("preview").style.visibility = "visible";
    setError("err-preview");
    $("send").disabled = false;
  } else {
    $("preview").style.visibility = "hidden";
    setError("err-preview", j.error);
    $("send").disabled = true;
  }
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files && fileInput.files[0];
  fileInput.value = "";               // so the same photo can be picked again
  if (!file) return;
  setError("err-start");
  show("s-wait");
  const my = ++reqSeq;
  try {
    let blob;
    try { blob = await shrink(file); } catch (e) { blob = file; }  // fallback: send the original
    const r = await post(`/api/process?sensitivity=${sens.value}`, blob, blob.type || "image/jpeg");
    const j = await r.json();
    if (my !== reqSeq) return;
    if (!j.token) { show("s-home"); setError("err-start", j.error || MSG.badImage); return; }
    token = j.token;
    applyResult(j);
    show("s-preview");
  } catch (e) {
    show("s-home");
    setError("err-start", MSG.network);
  }
});

let debounce = null;
sens.addEventListener("input", () => {
  localStorage.setItem("sensitivity", sens.value);
  clearTimeout(debounce);
  debounce = setTimeout(reprocess, 250);
});

async function reprocess() {
  if (!token) return;
  const my = ++reqSeq;
  busy(true);
  try {
    const r = await post(`/api/process?token=${token}&sensitivity=${sens.value}`, null);
    const j = await r.json();
    if (my !== reqSeq) return;
    if (r.status === 410) { show("s-home"); setError("err-start", j.error); return; }
    applyResult(j);
  } catch (e) {
    if (my === reqSeq) setError("err-preview", MSG.network);
  } finally {
    if (my === reqSeq) busy(false);
  }
}

function takePicture() {
  token = null; ++reqSeq;
  clearTimeout(doneTimer);
  show("s-home");
  fileInput.click();
}
$("retake").addEventListener("click", takePicture);
$("again").addEventListener("click", takePicture);
$("emptyTake").addEventListener("click", takePicture);
$("homeBtn").addEventListener("click", () => { clearTimeout(doneTimer); show("s-home"); });

$("send").addEventListener("click", async () => {
  if (!token || sending) return;
  sending = true;
  $("send").disabled = true;
  busy(true);
  try {
    const r = await post("/api/send", JSON.stringify({ token, sensitivity: Number(sens.value) }), "application/json");
    const j = await r.json();
    if (!j.ok) { setError("err-preview", j.error); if (r.status === 410) show("s-home"); return; }
    token = null;
    const sent = $("sentImg");
    sent.src = $("preview").src;
    sent.style.animation = "none"; void sent.offsetWidth; sent.style.animation = "";  // replay the rise
    show("s-done");
    clearTimeout(doneTimer);
    doneTimer = setTimeout(() => show("s-home"), 10000);
  } catch (e) {
    setError("err-preview", MSG.network);
  } finally {
    sending = false; busy(false); $("send").disabled = false;
  }
});

// ------------------------------------------------------------------ photos ----
function ago(created) {
  const s = Math.max(0, Date.now() / 1000 - created);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  return new Date(created * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

async function openGallery() {
  show("s-gallery");
  let list = [];
  try { list = (await listDrawings()).reverse(); }   // newest first
  catch (e) { toast("The laptop can't be reached"); }
  renderGallery(list);
}

function renderGallery(list) {
  const grid = $("grid");
  grid.innerHTML = "";
  $("galleryCount").textContent = list.length ? `(${list.length})` : "";
  $("empty").hidden = list.length > 0;
  $("galleryFoot").hidden = list.length === 0;
  for (const d of list) {
    const tile = document.createElement("div");
    tile.className = "tile";
    tile.dataset.id = d.id;
    const img = document.createElement("img");
    img.src = d.url; img.alt = "Drawing"; img.loading = "lazy";
    const when = document.createElement("span");
    when.className = "when"; when.textContent = ago(d.created);
    const del = document.createElement("button");
    del.className = "del"; del.setAttribute("aria-label", "Delete this drawing");
    del.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>';
    del.onclick = () => deleteOne(d, tile);
    tile.append(img, when, del);
    grid.append(tile);
  }
}

async function deleteOne(d, tile) {
  const ok = await confirmSheet({ title: "Delete this drawing?", text: "It disappears from the sky.", yes: "Delete", img: d.url });
  if (!ok) return;
  tile.classList.add("going");
  try {
    const r = await adminFetch(`/api/drawings/${d.id}`, "DELETE");
    if (!r || !r.ok) { tile.classList.remove("going"); if (r) toast(refusedMessage(r)); return; }
    tile.remove();
    const left = $("grid").children.length;
    $("galleryCount").textContent = left ? `(${left})` : "";
    $("empty").hidden = left > 0;
    $("galleryFoot").hidden = left === 0;
    toast("Drawing deleted");
  } catch (e) {
    tile.classList.remove("going");
    toast("The laptop can't be reached");
  }
}

async function deleteAll() {
  let n = 0;
  try { n = (await listDrawings()).length; } catch (e) { toast("The laptop can't be reached"); return; }
  if (n === 0) { toast("There are no drawings to delete"); return; }
  const ok = await confirmSheet({ title: `Delete all ${plural(n, "drawing", "drawings")}?`,
                                  text: "They all disappear from the sky. The laptop keeps a copy in drawings/_trash.",
                                  yes: "Delete all", no: "Keep them" });
  if (!ok) return;
  try {
    const r = await adminFetch("/api/clear", "POST");
    if (!r || !r.ok) { if (r) toast(refusedMessage(r)); return; }
    const j = await r.json();
    toast(`${plural(j.moved, "drawing", "drawings")} deleted`);
    if ($("s-gallery").classList.contains("show")) renderGallery([]);
    refreshCount();
  } catch (e) { toast("The laptop can't be reached"); }
}

$("photosBtn").addEventListener("click", openGallery);
$("backBtn").addEventListener("click", () => show("s-home"));
$("clearBtn2").addEventListener("click", deleteAll);
