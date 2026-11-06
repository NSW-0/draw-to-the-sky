"""
Draw to the Sky — local server for a kids' astronomy event.

    pip install -r requirements.txt
    python server.py

Laptop:  http://localhost:3000/sky      (press F = fullscreen, D = delete mode)
QR code: http://localhost:3000/connect  (open on a second screen or tablet; phones scan it)
Phone:   http://<laptop-ip>:3000/capture (printed at start-up)
"""

# ============================== CONFIG =======================================
import os as _os
PORT = int(_os.environ.get("STAR_PORT", 3000))
HOST = "0.0.0.0"                 # listen on all networks so the phone can reach us
DRAWINGS_DIR = _os.environ.get("STAR_DRAWINGS_DIR", "drawings")   # saved PNGs live here (survive restarts)
DEFAULT_SENSITIVITY = 50         # 0..100, starting value of the slider on the phone
USE_REMBG = False                # True = try the rembg model first (needs `pip install rembg`)
MAX_UPLOAD_MB = 15
OPEN_BROWSER = _os.environ.get("STAR_NO_BROWSER") is None   # open the Sky + QR pages on start
ADMIN_PIN = ""                 # e.g. "4321": phones must enter it once before deleting.
                                 # "" = any phone on the Wi-Fi can delete (the laptop always can)
# =============================================================================

import asyncio
import io
import json
import os
import secrets
import shutil
import socket
import time
import base64
from collections import OrderedDict

import qrcode
import qrcode.image.svg
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

import imageproc

BASE = os.path.dirname(os.path.abspath(__file__))
DRAW_DIR = os.path.join(BASE, DRAWINGS_DIR)
STATIC_DIR = os.path.join(BASE, "static")
os.makedirs(DRAW_DIR, exist_ok=True)


# ------------------------------------------------------------- networking ----
def _is_private(ip):
    p = [int(x) for x in ip.split(".")]
    return p[0] == 10 or (p[0] == 172 and 16 <= p[1] <= 31) or (p[0] == 192 and p[1] == 168)


def local_ips():
    """All IPv4 addresses of this machine on a local network, best guess first."""
    found = []
    try:  # the address used for the default route (no packet is actually sent)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.254.254.254", 1))
        found.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    out = []
    for ip in found:
        if ip not in out and not ip.startswith("127.") and not ip.startswith("169.254."):
            out.append(ip)
    out.sort(key=lambda ip: (not _is_private(ip), not ip.startswith("192.168."), found.index(ip)))
    return out


_net = {"t": 0.0, "ips": []}


def current_ips():
    """Re-checked every few seconds, so switching to a hotspot or USB cable needs no restart."""
    if time.time() - _net["t"] > 5:
        _net["ips"], _net["t"] = local_ips(), time.time()
    return _net["ips"]


def capture_url(ip=None):
    ips = current_ips()
    return f"http://{ip or (ips[0] if ips else '127.0.0.1')}:{PORT}/capture"


def is_laptop(request: Request):
    host = request.client.host if request.client else ""
    if host.startswith("::ffff:"):          # IPv4 client seen through the dual-stack socket
        host = host[7:]
    return host in ("127.0.0.1", "::1", "localhost") or host in local_ips()


def admin_allowed(request: Request):
    """Delete / delete-all: the laptop always; phones too, with the PIN if one is set."""
    if is_laptop(request) or not ADMIN_PIN:
        return True
    return secrets.compare_digest(request.headers.get("x-admin-pin", ""), ADMIN_PIN)


# ----------------------------------------------------------------- events ----
class Hub:
    def __init__(self):
        self.clients = set()

    def subscribe(self):
        q = asyncio.Queue(maxsize=100)
        self.clients.add(q)
        return q

    def unsubscribe(self, q):
        self.clients.discard(q)

    def publish(self, event):
        for q in list(self.clients):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass


hub = Hub()


# ---------------------------------------------------------------- storage ----
def list_drawings():
    items = []
    for name in sorted(os.listdir(DRAW_DIR)):
        if name.lower().endswith(".png"):
            did = name[:-4]
            try:
                created = int(did.split("-")[0]) / 1000
            except ValueError:
                created = os.path.getmtime(os.path.join(DRAW_DIR, name))
            items.append({"id": did, "url": f"/drawings/{name}", "created": created})
    items.sort(key=lambda d: d["created"])
    return items


def safe_id(did):
    if not did or not all(c.isascii() and (c.isalnum() or c in "-_") for c in did):
        raise HTTPException(400, "bad id")
    return did


class PendingCache:
    """Recent uploads (already resized) so the slider can re-process quickly."""

    def __init__(self, size=30):
        self.size = size
        self.items = OrderedDict()

    def put(self, img):
        token = secrets.token_hex(8)
        self.items[token] = img
        while len(self.items) > self.size:
            self.items.popitem(last=False)
        return token

    def get(self, token):
        img = self.items.get(token)
        if img is not None:
            self.items.move_to_end(token)
        return img


pending = PendingCache()

# ------------------------------------------------------------------- app -----
app = FastAPI(title="Draw to the Sky", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/drawings", StaticFiles(directory=DRAW_DIR), name="drawings")

NO_CACHE = {"Cache-Control": "no-store"}
ERR_NO_DRAWING = "No drawing found in this photo. Add more light, or move the slider toward More."
ERR_BAD_IMAGE = "This photo can't be read. Take it again."
ERR_EXPIRED = "This photo is no longer on the laptop. Take it again."


def err(status, msg):
    return JSONResponse({"ok": False, "error": msg}, status, headers=NO_CACHE)


@app.get("/")
def root():
    return RedirectResponse("/sky")


@app.get("/sky")
def sky():
    return FileResponse(os.path.join(STATIC_DIR, "sky.html"), headers=NO_CACHE)


@app.get("/capture")
@app.get("/c")
def capture():
    return FileResponse(os.path.join(STATIC_DIR, "capture.html"), headers=NO_CACHE)


@app.get("/connect")
@app.get("/qr")
def connect_page():
    return FileResponse(os.path.join(STATIC_DIR, "connect.html"), headers=NO_CACHE)


@app.get("/api/info")
def info():
    return JSONResponse({"capture_url": capture_url(), "ips": current_ips(), "port": PORT,
                         "default_sensitivity": DEFAULT_SENSITIVITY, "pin_required": bool(ADMIN_PIN)}, headers=NO_CACHE)


@app.get("/api/qr.svg")
def qr_svg():
    img = qrcode.make(capture_url(), image_factory=qrcode.image.svg.SvgPathFillImage, border=2, box_size=10)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml", headers=NO_CACHE)


@app.get("/api/drawings")
def drawings():
    return JSONResponse(list_drawings(), headers=NO_CACHE)


def _run_cutout(img, sensitivity):
    return imageproc.cutout(img, sensitivity, use_rembg=USE_REMBG)


@app.post("/api/process")
async def process(request: Request, sensitivity: float = DEFAULT_SENSITIVITY, token: str = ""):
    body = await request.body()
    if len(body) > MAX_UPLOAD_MB * 1024 * 1024:
        return err(413, ERR_BAD_IMAGE)
    if body:
        try:
            img = await run_in_threadpool(imageproc.prepare, body)
        except Exception:
            return err(400, ERR_BAD_IMAGE)
        token = pending.put(img)
    else:
        img = pending.get(token)
        if img is None:
            return err(410, ERR_EXPIRED)
    try:
        res = await run_in_threadpool(_run_cutout, img, sensitivity)
    except imageproc.NoDrawingFound:
        return JSONResponse({"ok": False, "token": token, "error": ERR_NO_DRAWING}, 200, headers=NO_CACHE)
    preview = "data:image/png;base64," + base64.b64encode(res["png"]).decode()
    return JSONResponse({"ok": True, "token": token, "preview": preview}, headers=NO_CACHE)


@app.post("/api/send")
async def send(request: Request):
    try:
        data = await request.json()
        token = str(data.get("token", ""))
        sensitivity = float(data.get("sensitivity", DEFAULT_SENSITIVITY))
    except Exception:
        return err(400, ERR_BAD_IMAGE)
    img = pending.get(token)
    if img is None:
        return err(410, ERR_EXPIRED)
    try:
        res = await run_in_threadpool(_run_cutout, img, sensitivity)
    except imageproc.NoDrawingFound:
        return err(422, ERR_NO_DRAWING)
    did = f"{int(time.time() * 1000)}-{secrets.token_hex(3)}"
    path = os.path.join(DRAW_DIR, did + ".png")
    with open(path + ".tmp", "wb") as f:
        f.write(res["png"])
    os.replace(path + ".tmp", path)
    pending.items.pop(token, None)   # one photo = one drawing
    item = {"id": did, "url": f"/drawings/{did}.png", "created": time.time()}
    hub.publish({"type": "add", "drawing": item})
    print(f"  + new drawing {did}  ({res['size'][0]}x{res['size'][1]})")
    return JSONResponse({"ok": True, "drawing": item}, headers=NO_CACHE)


@app.delete("/api/drawings/{did}")
def delete_drawing(did: str, request: Request):
    if not admin_allowed(request):
        return JSONResponse({"ok": False, "need_pin": True, "error": "Wrong PIN."}, 403, headers=NO_CACHE)
    did = safe_id(did)
    path = os.path.join(DRAW_DIR, did + ".png")
    if os.path.exists(path):
        trash = os.path.join(DRAW_DIR, "_trash")
        os.makedirs(trash, exist_ok=True)
        shutil.move(path, os.path.join(trash, did + ".png"))
    hub.publish({"type": "remove", "id": did})
    return {"ok": True}


@app.post("/api/clear")
def clear_all(request: Request):
    if not admin_allowed(request):
        return JSONResponse({"ok": False, "need_pin": True, "error": "Wrong PIN."}, 403, headers=NO_CACHE)
    trash =os.path.join(DRAW_DIR, "_trash", time.strftime("%Y%m%d-%H%M%S"))
    moved = 0
    for d in list_drawings():
        os.makedirs(trash, exist_ok=True)
        shutil.move(os.path.join(DRAW_DIR, d["id"] + ".png"), os.path.join(trash, d["id"] + ".png"))
        moved += 1
    hub.publish({"type": "clear"})
    print(f"  cleared {moved} drawings (moved to {trash})")
    return {"ok": True, "moved": moved}


@app.get("/api/events")
async def events(request: Request):
    q = hub.subscribe()

    async def stream():
        try:
            yield "retry: 2000\n\n"
            yield f"data: {json.dumps({'type': 'hello'})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(ev)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            hub.unsubscribe(q)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


def dual_stack_socket(port):
    """
    Listen on IPv4 AND IPv6 at once. On Windows, "localhost" tries IPv6 (::1) first;
    with an IPv4-only server every request from the laptop itself waits ~2 s.
    Returns None if IPv6 isn't available (then uvicorn uses plain IPv4).
    """
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR if os.name != "nt" else socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind(("::", port))
        s.listen(128)
        s.set_inheritable(True)
        return s
    except (OSError, AttributeError):
        return None


def banner():
    line = "=" * 64
    print(line)
    print("  DRAW TO THE SKY is running")
    print(line)
    print(f"  Big screen (sky):      http://localhost:{PORT}/sky")
    print(f"  QR code for phones:    http://localhost:{PORT}/connect")
    ips = current_ips()
    print(f"  Phone (same network):  {capture_url()}")
    for ip in ips[1:]:
        print(f"     ...or try:          {capture_url(ip)}")
    if not ips:
        print("  !! No network yet. Connect Wi-Fi, a hotspot or a USB cable - the QR page updates by itself.")
    print()
    print("  Sky page keys: F = fullscreen, D = delete mode")
    print("  If Windows asks about the firewall: allow Python on PRIVATE networks.")
    print(f"  Drawings are saved in: {DRAW_DIR}")
    print("  Press Ctrl+C to stop.")
    print(line)


def open_pages():
    """Open the big-screen page and the QR page in the browser."""
    import webbrowser
    webbrowser.open_new(f"http://localhost:{PORT}/connect")
    time.sleep(0.8)
    webbrowser.open_new_tab(f"http://localhost:{PORT}/sky")   # opened last = the tab in front


def already_running():
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/info", timeout=1.5) as r:
            return "capture_url" in json.loads(r.read())
    except Exception:
        return False


def open_when_ready():
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", PORT), timeout=0.3).close()
            open_pages()
            return
        except OSError:
            time.sleep(0.1)


if __name__ == "__main__":
    if already_running():
        print("  Draw to the Sky is already running - opening the pages again.")
        if OPEN_BROWSER:
            open_pages()
        raise SystemExit(0)
    if USE_REMBG:
        try:
            import rembg  # noqa: F401
            print("  rembg mode ON")
        except Exception:
            print("  !! USE_REMBG is True but rembg is not installed - using classic mode")
    banner()
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning", timeout_graceful_shutdown=1)
    server = uvicorn.Server(config)
    sock = dual_stack_socket(PORT) if HOST in ("0.0.0.0", "::") else None
    if OPEN_BROWSER:
        import threading
        threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        server.run(sockets=[sock] if sock else None)
    except KeyboardInterrupt:
        pass   # Ctrl+C: uvicorn already shut down cleanly; don't print a traceback
    print("  Stopped. Drawings are saved - start again any time.")
