/* Draw to the Sky — the big-screen page.
 * Keys: F = fullscreen, D = delete mode (click a drawing to remove it)
 * The QR code for phones is on a separate page: /connect
 */

// ============================== CONFIG ======================================
const CONFIG = {
  // background
  backgroundImage: "/static/space.jpg", // swap for any space photo
  backgroundMoves: true,        // slow pan + zoom of the background photo
  backgroundZoom: 1.12,         // how much bigger than the screen (room to pan)
  backgroundCycleSeconds: 140,  // time for one slow pan loop
  twinkles: 45,                 // extra twinkling stars on top of the photo
  shootingStarEvery: [6, 15],   // seconds between shooting stars (random)

  // drawings
  maxOnScreen: 60,              // more than this -> oldest fades out (stays on disk)
  drawingSize: [0.11, 0.20],    // long side as a fraction of screen height (random)
  shrinkWhenCrowded: true,      // make everyone a bit smaller when there are many drawings
  driftSpeed: [12, 34],         // pixels per second
  spinSpeed: [2, 8],            // degrees per second (random direction)
  bobAmount: [5, 12],           // pixels up/down
  bobPeriod: [4, 8],            // seconds per bob
  edgeSpring: 3.0,              // how softly drawings bounce off the edges (lower = softer)
  fadeOutSeconds: 2.0,          // when removed / too many

  // arrival of a new drawing
  entranceSeconds: 1.4,         // fade-and-grow
  glowSeconds: 7,               // how long a new drawing glows and sparkles, then it stops
  // each new drawing gets ONE of these glow colours (r, g, b), taking turns so neighbours differ
  glowColors: [
    "255, 214, 110",            // gold
    "110, 200, 255",            // sky blue
    "255, 120, 200",            // pink
    "140, 255, 160",            // mint green
  ],
  glowSize: 36,                 // px of glow
  haloStrength: 0.55,           // soft warm light behind a new drawing (0 = none)
  newSizeBoost: 1.35,           // a new drawing starts this much bigger, then settles to normal
  sparklesPerSecond: 16,        // little stars around a new drawing
  sparkleSize: [16, 36],        // px
  spriteMaxPx: 520,             // internal resolution of each drawing
};
// ============================================================================

const canvas = document.getElementById("sky");
const ctx = canvas.getContext("2d");
let W = 0, H = 0, DPR = 1;
const rand = (a, b) => a + Math.random() * (b - a);
const randIn = (r) => rand(r[0], r[1]);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

// ------------------------------------------------------------ background ----
const bgImg = new Image();
let bgReady = false;
bgImg.onload = () => { bgReady = true; };
bgImg.src = CONFIG.backgroundImage;
let bgRect = { x: 0, y: 0, w: 1, h: 1 };

function drawBackground(t) {
  ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H);
  if (!bgReady) return;
  const cover = Math.max(W / bgImg.naturalWidth, H / bgImg.naturalHeight);
  let zoom = CONFIG.backgroundZoom, px = 0.5, py = 0.5;
  if (CONFIG.backgroundMoves) {
    const p = (t / CONFIG.backgroundCycleSeconds) * Math.PI * 2;
    zoom *= 1 + 0.035 * Math.sin(p * 0.5);
    px = 0.5 + 0.5 * Math.sin(p);          // 0..1 across the free margin
    py = 0.5 + 0.5 * Math.sin(p * 0.7 + 1.3);
  }
  const w = bgImg.naturalWidth * cover * zoom, h = bgImg.naturalHeight * cover * zoom;
  bgRect = { x: -(w - W) * px, y: -(h - H) * py, w, h };
  ctx.drawImage(bgImg, bgRect.x, bgRect.y, w, h);
}

// twinkling stars pinned to the photo (they move with it)
const twinkles = [];
let flareSprite = null;
function buildFlare() {
  const s = 64, c = document.createElement("canvas");
  c.width = c.height = s;
  const g = c.getContext("2d");
  const rg = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  rg.addColorStop(0, "rgba(255,255,255,1)"); rg.addColorStop(0.12, "rgba(255,255,255,0.8)");
  rg.addColorStop(0.35, "rgba(200,220,255,0.15)"); rg.addColorStop(1, "rgba(200,220,255,0)");
  g.fillStyle = rg; g.fillRect(0, 0, s, s);
  g.strokeStyle = "rgba(255,255,255,0.7)"; g.lineWidth = 1.2;
  g.beginPath(); g.moveTo(s / 2, 4); g.lineTo(s / 2, s - 4); g.moveTo(4, s / 2); g.lineTo(s - 4, s / 2); g.stroke();
  flareSprite = c;
}
for (let i = 0; i < CONFIG.twinkles; i++) {
  twinkles.push({ u: Math.random(), v: Math.random(), size: rand(8, 20), ph: rand(0, 6.28), sp: rand(0.4, 1.4) });
}
function drawTwinkles(t) {
  ctx.globalCompositeOperation = "lighter";
  for (const s of twinkles) {
    const a = Math.pow(0.5 + 0.5 * Math.sin(t * s.sp * Math.PI * 2 * 0.5 + s.ph), 3);
    if (a < 0.02) continue;
    const x = bgRect.x + s.u * bgRect.w, y = bgRect.y + s.v * bgRect.h, z = s.size * (0.6 + 0.4 * a);
    ctx.globalAlpha = a * 0.9;
    ctx.drawImage(flareSprite, x - z / 2, y - z / 2, z, z);
  }
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = "source-over";
}

let shooting = null, nextShoot = rand(3, 6);
function drawShootingStar(t, dt) {
  if (!shooting && t > nextShoot) {
    const fromLeft = Math.random() < 0.5;
    const ang = (fromLeft ? rand(15, 35) : rand(145, 165)) * Math.PI / 180;
    shooting = { x: fromLeft ? rand(-50, W * 0.5) : rand(W * 0.5, W + 50), y: rand(-30, H * 0.35),
                 vx: Math.cos(ang) * rand(900, 1400), vy: Math.sin(ang) * rand(900, 1400),
                 life: 0, max: rand(0.8, 1.3), len: rand(140, 240) };
  }
  if (!shooting) return;
  const s = shooting;
  s.life += dt; s.x += s.vx * dt; s.y += s.vy * dt;
  const k = s.life / s.max;
  const alpha = Math.sin(Math.PI * clamp(k, 0, 1));
  const sp = Math.hypot(s.vx, s.vy);
  const tx = s.x - (s.vx / sp) * s.len, ty = s.y - (s.vy / sp) * s.len;
  const g = ctx.createLinearGradient(s.x, s.y, tx, ty);
  g.addColorStop(0, `rgba(255,255,255,${alpha})`);
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.strokeStyle = g; ctx.lineWidth = 2.2; ctx.lineCap = "round";
  ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(tx, ty); ctx.stroke();
  if (k >= 1) { shooting = null; nextShoot = t + randIn(CONFIG.shootingStarEvery); }
}

// --------------------------------------------------------------- drawings ----
const drawings = new Map(); // id -> drawing
// halo + sparkle images, one pair per glow colour (built once, reused)
const glowArt = new Map();
let nextGlow = Math.floor(Math.random() * CONFIG.glowColors.length);

function lighter(rgb) {   // sparkle centres: a paler version of the colour
  return rgb.split(",").map((v) => Math.round(Number(v) + (255 - Number(v)) * 0.55)).join(",");
}

function getGlowArt(rgb) {
  if (glowArt.has(rgb)) return glowArt.get(rgb);
  // soft halo
  const hs = 256, halo = document.createElement("canvas");
  halo.width = halo.height = hs;
  let g = halo.getContext("2d");
  let rg = g.createRadialGradient(hs / 2, hs / 2, 0, hs / 2, hs / 2, hs / 2);
  rg.addColorStop(0, `rgba(${rgb},0.8)`); rg.addColorStop(0.5, `rgba(${rgb},0.25)`); rg.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = rg; g.fillRect(0, 0, hs, hs);
  // 4-pointed twinkle star with a soft core
  const s = 64, m = s / 2, sparkle = document.createElement("canvas");
  sparkle.width = sparkle.height = s;
  g = sparkle.getContext("2d");
  rg = g.createRadialGradient(m, m, 0, m, m, m * 0.5);
  rg.addColorStop(0, `rgba(${rgb},0.95)`); rg.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = rg; g.fillRect(0, 0, s, s);
  g.fillStyle = `rgb(${lighter(rgb)})`;
  g.beginPath();
  for (let i = 0; i < 8; i++) {
    const r = i % 2 === 0 ? m * 0.95 : m * 0.16, a = (i * Math.PI) / 4 - Math.PI / 2;
    g.lineTo(m + r * Math.cos(a), m + r * Math.sin(a));
  }
  g.closePath(); g.fill();
  const art = { halo, sparkle };
  glowArt.set(rgb, art);
  return art;
}

function makeSprites(img, rgb) {
  const scale = Math.min(1, CONFIG.spriteMaxPx / Math.max(img.naturalWidth, img.naturalHeight));
  const w = Math.round(img.naturalWidth * scale), h = Math.round(img.naturalHeight * scale);
  const pad = Math.ceil(CONFIG.glowSize * 1.6);
  const mk = () => { const c = document.createElement("canvas"); c.width = w + pad * 2; c.height = h + pad * 2; return c; };
  const plain = mk();
  plain.getContext("2d").drawImage(img, pad, pad, w, h);
  const glow = mk();                       // used only while a new drawing is glowing
  const g = glow.getContext("2d");
  g.shadowColor = `rgb(${rgb})`; g.shadowBlur = CONFIG.glowSize;
  g.drawImage(img, pad, pad, w, h);
  g.drawImage(img, pad, pad, w, h);
  return { plain, glow, w, h, pad };
}

function addDrawing(item, { fresh }) {
  if (drawings.has(item.id)) return;
  const d = {
    id: item.id, created: item.created, sprite: null, state: "loading",
    x: 0, y: 0, vx: 0, vy: 0, angle: rand(-0.3, 0.3),
    spin: (randIn(CONFIG.spinSpeed) * (Math.random() < 0.5 ? -1 : 1) * Math.PI) / 180,
    speed: randIn(CONFIG.driftSpeed), sizeK: randIn(CONFIG.drawingSize),
    bobAmp: randIn(CONFIG.bobAmount), bobW: (Math.PI * 2) / randIn(CONFIG.bobPeriod), bobPh: rand(0, 6.28),
    age: 0, leaveT: 0, fresh, delay: fresh ? 0 : rand(0, 1.5), sparkles: [], sparkleAcc: 0,
    glowRgb: CONFIG.glowColors[fresh ? nextGlow++ % CONFIG.glowColors.length : 0],
  };
  d.art = getGlowArt(d.glowRgb);
  drawings.set(item.id, d);
  const img = new Image();
  img.onload = () => {
    if (!drawings.has(d.id)) return;
    d.sprite = makeSprites(img, d.glowRgb);
    const dir = rand(0, Math.PI * 2);
    d.vx = Math.cos(dir) * d.speed; d.vy = Math.sin(dir) * d.speed;
    if (fresh) { d.x = W / 2 + rand(-0.12, 0.12) * W; d.y = H / 2 + rand(-0.1, 0.1) * H; }
    else { d.x = rand(0.1, 0.9) * W; d.y = rand(0.12, 0.88) * H; }
    d.state = "enter";
    enforceLimit();
  };
  img.onerror = () => drawings.delete(d.id);
  img.src = item.url;
}

function removeDrawing(id) {
  const d = drawings.get(id);
  if (!d) return;
  if (d.state === "loading") { drawings.delete(id); return; }
  if (d.state !== "leave") { d.state = "leave"; d.leaveT = 0; }
}

function enforceLimit() {
  const live = [...drawings.values()].filter((d) => d.state !== "leave").sort((a, b) => a.created - b.created);
  for (let i = 0; i < live.length - CONFIG.maxOnScreen; i++) removeDrawing(live[i].id);
}

const easeOutBack = (x) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
let crowd = 1;

function glowAmount(d) {
  // 1 while new, fading smoothly to exactly 0 at glowSeconds
  if (!d.fresh || d.state === "leave" || d.age >= CONFIG.glowSeconds) return 0;
  const tail = 2.5, left = CONFIG.glowSeconds - d.age;
  const base = left < tail ? left / tail : 1;
  return base * (0.75 + 0.25 * Math.sin(d.age * Math.PI * 2 * 0.8));
}

function updateSparkles(d, dt, radius) {
  const emitting = d.fresh && d.state !== "leave" && d.age < CONFIG.glowSeconds - 1;
  if (emitting) {
    d.sparkleAcc += dt * CONFIG.sparklesPerSecond * (d.age < 1.2 ? 3 : 1);  // a burst on arrival
    while (d.sparkleAcc >= 1) {
      d.sparkleAcc -= 1;
      const a = rand(0, Math.PI * 2), r0 = radius * rand(0.6, 1.2);
      d.sparkles.push({ ox: Math.cos(a) * r0, oy: Math.sin(a) * r0, vx: Math.cos(a) * rand(25, 70), vy: Math.sin(a) * rand(25, 70) - 10,
                        life: 0, max: rand(1.0, 1.9), size: randIn(CONFIG.sparkleSize), rot: rand(0, 1.6), spin: rand(-1.5, 1.5) });
    }
  }
  for (const s of d.sparkles) { s.life += dt; s.ox += s.vx * dt; s.oy += s.vy * dt; s.rot += s.spin * dt; }
  d.sparkles = d.sparkles.filter((s) => s.life < s.max);
}

function drawSparkles(d, cx, cy, alpha) {
  if (!d.sparkles.length) return;
  ctx.globalCompositeOperation = "lighter";
  for (const s of d.sparkles) {
    const k = s.life / s.max, a = Math.sin(Math.PI * k), z = s.size * (0.5 + 0.7 * a);
    ctx.save();
    ctx.globalAlpha = a * alpha;
    ctx.translate(cx + s.ox, cy + s.oy); ctx.rotate(s.rot);
    ctx.drawImage(d.art.sparkle, -z / 2, -z / 2, z, z);
    ctx.restore();
  }
  ctx.globalCompositeOperation = "source-over";
  ctx.globalAlpha = 1;
}

function updateAndDraw(t, dt) {
  const live = [...drawings.values()].filter((d) => d.sprite);
  if (CONFIG.shrinkWhenCrowded) {
    const target = clamp(1.15 - live.length / 70, 0.6, 1.1);
    crowd += (target - crowd) * Math.min(1, dt * 0.5);
  }
  live.sort((a, b) => a.created - b.created);  // newest on top
  for (const d of live) {
    if (d.delay > 0) { d.delay -= dt; continue; }
    d.age += dt;
    const sp = d.sprite;
    const long = d.sizeK * H * crowd;
    const scale = long / Math.max(sp.w, sp.h);
    const r = (Math.max(sp.w, sp.h) * scale) / 2 * 0.85;   // bounce radius

    // motion
    d.x += d.vx * dt; d.y += d.vy * dt; d.angle += d.spin * dt;
    const k = CONFIG.edgeSpring;
    if (d.x < r) d.vx += (r - d.x) * k * dt;
    if (d.x > W - r) d.vx -= (d.x - (W - r)) * k * dt;
    if (d.y < r) d.vy += (r - d.y) * k * dt;
    if (d.y > H - r) d.vy -= (d.y - (H - r)) * k * dt;
    const v = Math.hypot(d.vx, d.vy) || 1;
    const f = 1 + (d.speed / v - 1) * Math.min(1, dt * 0.6);
    d.vx *= f; d.vy *= f;

    // look
    let s = 1, alpha = 1;
    if (d.state === "enter") {
      const e = clamp(d.age / CONFIG.entranceSeconds, 0, 1);
      s = d.fresh ? Math.max(0.01, easeOutBack(e)) : 0.85 + 0.15 * e;
      alpha = clamp(e * 1.6, 0, 1);
      if (e >= 1) d.state = "live";
    } else if (d.state === "leave") {
      d.leaveT += dt;
      const e = clamp(d.leaveT / CONFIG.fadeOutSeconds, 0, 1);
      alpha = 1 - e; s = 1 - 0.35 * e;
      if (e >= 1) { drawings.delete(d.id); continue; }
    }
    if (d.fresh && d.age < CONFIG.glowSeconds) {
      const fade = 1 - d.age / CONFIG.glowSeconds;
      s *= 1 + (CONFIG.newSizeBoost - 1) * fade * fade * (3 - 2 * fade);   // settles to normal size
    }
    const glow = glowAmount(d);
    const by = d.y + Math.sin(t * d.bobW + d.bobPh) * d.bobAmp;
    d._hit = { x: d.x, y: by, a: d.angle, hw: (sp.w * scale * s) / 2, hh: (sp.h * scale * s) / 2 };
    updateSparkles(d, dt, long * s * 0.5);

    ctx.save();
    ctx.translate(d.x, by);
    if (glow > 0.001 && CONFIG.haloStrength > 0) {
      const hr = long * s * 0.95;
      ctx.globalAlpha = alpha * glow * CONFIG.haloStrength;
      ctx.drawImage(d.art.halo, -hr, -hr, hr * 2, hr * 2);
    }
    ctx.rotate(d.angle);
    const sc = scale * s;
    const x0 = -(sp.w / 2 + sp.pad) * sc, y0 = -(sp.h / 2 + sp.pad) * sc;
    const ww = sp.plain.width * sc, hh = sp.plain.height * sc;
    if (glow > 0.001) {
      ctx.globalAlpha = alpha * glow;
      ctx.drawImage(sp.glow, x0, y0, ww, hh);
    }
    ctx.globalAlpha = alpha;
    ctx.drawImage(sp.plain, x0, y0, ww, hh);
    if (admin && hovered === d) {
      ctx.globalAlpha = 1; ctx.strokeStyle = "#E9825A"; ctx.lineWidth = 4;
      ctx.strokeRect(-(sp.w / 2) * sc, -(sp.h / 2) * sc, sp.w * sc, sp.h * sc);
    }
    ctx.restore();
    drawSparkles(d, d.x, by, alpha);
  }
}

// ------------------------------------------------------------------ loop ----
let last = performance.now(), fpsEMA = 60;
window.skyStats = { fps: 60, drawings: 0 };
function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  if (dt > 0) fpsEMA += (1 / dt - fpsEMA) * 0.05;
  const t = now / 1000;
  if (window.innerWidth !== W || window.innerHeight !== H) resize();
  ctx.setTransform(DPR, 0, 0, canvas.height / H, 0, 0);
  drawBackground(t);
  drawTwinkles(t);
  drawShootingStar(t, dt);
  updateAndDraw(t, dt);
  window.skyStats.fps = Math.round(fpsEMA);
  window.skyStats.drawings = drawings.size;
  requestAnimationFrame(frame);
}

function resize() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  W = window.innerWidth; H = window.innerHeight;
  canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
  DPR = canvas.width / W;    // exact scale (devicePixelRatio can be 1.0000000149)
  for (const d of drawings.values()) { d.x = clamp(d.x, 0, W); d.y = clamp(d.y, 0, H); }
}

// --------------------------------------------------------------- network ----
let loadedOnce = false;
async function sync() {
  try {
    const list = await (await fetch("/api/drawings", { cache: "no-store" })).json();
    const ids = new Set(list.map((d) => d.id));
    for (const id of [...drawings.keys()]) if (!ids.has(id)) removeDrawing(id);
    const newest = list.slice(-CONFIG.maxOnScreen);
    for (const item of newest) addDrawing(item, { fresh: loadedOnce && Date.now() / 1000 - item.created < 30 });
    loadedOnce = true;
  } catch (e) { console.warn("sync failed", e); }
}

function connect() {
  const es = new EventSource("/api/events");
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === "hello") sync();
    else if (ev.type === "add") addDrawing(ev.drawing, { fresh: true });
    else if (ev.type === "remove") removeDrawing(ev.id);
    else if (ev.type === "clear") for (const id of [...drawings.keys()]) removeDrawing(id);
  };
  // EventSource reconnects by itself; "hello" on reconnect triggers a re-sync
}

// ------------------------------------------------------------------- keys ----
let admin = false, hovered = null;

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg; el.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.remove("show"), 2500);
}

function setAdmin(on) {
  admin = on;
  document.body.classList.toggle("admin", on);
  updateCount();
}
function updateCount() {
  const n = [...drawings.values()].filter((d) => d.state !== "leave").length;
  document.getElementById("count").textContent = n === 1 ? "1 drawing on screen" : `${n} drawings on screen`;
}
setInterval(() => admin && updateCount(), 500);

const modal = document.getElementById("modal");
function showModal(on) { modal.classList.toggle("show", on); }

document.addEventListener("keydown", (e) => {
  if (modal.classList.contains("show")) {
    if (e.key === "Escape") showModal(false);
    return;
  }
  const k = e.key.toLowerCase();
  if (k === "f") {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
    else document.exitFullscreen?.();
  } else if (k === "d") {
    setAdmin(!admin);
  } else if (k === "escape" && admin) {
    setAdmin(false);
  }
});

function hitTest(px, py) {
  const list = [...drawings.values()].filter((d) => d._hit && d.state !== "leave").sort((a, b) => b.created - a.created);
  for (const d of list) {
    const h = d._hit, dx = px - h.x, dy = py - h.y;
    const c = Math.cos(-h.a), s = Math.sin(-h.a);
    const lx = dx * c - dy * s, ly = dx * s + dy * c;
    if (Math.abs(lx) <= h.hw && Math.abs(ly) <= h.hh) return d;
  }
  return null;
}

canvas.addEventListener("mousemove", (e) => { if (admin) hovered = hitTest(e.clientX, e.clientY); });
canvas.addEventListener("click", async (e) => {
  if (!admin) return;
  const d = hitTest(e.clientX, e.clientY);
  if (!d) return;
  const res = await fetch(`/api/drawings/${d.id}`, { method: "DELETE" });
  if (res.ok) { removeDrawing(d.id); toast("Drawing removed"); }
  else toast("Drawings can only be removed on the laptop running the server");
});
document.getElementById("clearBtn").onclick = () => showModal(true);
document.getElementById("noBtn").onclick = () => showModal(false);
document.getElementById("yesBtn").onclick = async () => {
  showModal(false);
  const res = await fetch("/api/clear", { method: "POST" });
  if (res.ok) { const j = await res.json(); toast(j.moved === 1 ? "1 drawing removed" : `${j.moved} drawings removed`); }
  else toast("Drawings can only be removed on the laptop running the server");
};

// hide the mouse pointer when idle
let idleTimer = null;
document.addEventListener("mousemove", () => {
  document.body.classList.remove("idle");
  clearTimeout(idleTimer);
  idleTimer = setTimeout(() => document.body.classList.add("idle"), 3000);
});

// ----------------------------------------------------------------- start ----
window.addEventListener("resize", resize);
resize();
buildFlare();
connect();
requestAnimationFrame((n) => { last = n; frame(n); });
