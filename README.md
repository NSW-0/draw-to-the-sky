# Draw to the Sky ✨

Kids draw a planet, star, rocket or alien on white paper. A helper photographs it with a phone,
the drawing is cut out automatically (offline, no internet needed) and it floats, bobs and slowly
spins across a space wallpaper on the laptop screen.

- **Laptop** runs a small server and shows the full-screen **Sky** page.
- **Connect** page (`/connect`) shows a big QR code. Open it on a second screen or tablet, or show it to the helpers before the event.
- **Phone** opens the **Capture** page over the same Wi-Fi (by scanning that QR code).

---

## Pictures (not included in this repo)

The app uses three pictures that you add yourself. Without them it still works, just with a plain black background.

| File | Used for | Tip |
|---|---|---|
| `static/space.jpg` | big-screen background | a wide space photo, about 1920×1080 or larger |
| `static/phone_bg.jpg` | phone background | a tall picture, at least 1170 px high looks sharp |
| `static/icon.ico` | icon for the desktop shortcut (optional) | any square picture saved as `.ico` |

To make a desktop shortcut with that icon on Windows: right-click `start.bat` → **Show more options** →
**Send to → Desktop (create shortcut)**, then right-click the shortcut → **Properties → Change Icon…**
and pick `static\icon.ico`.

## 1. Install (once, at home, with internet)

You need **Python 3.10 or newer** (tested with 3.13). On Windows, tick "Add Python to PATH" when installing.

```bash
cd Star
pip install -r requirements.txt
```

That installs 5 packages: `fastapi`, `uvicorn`, `opencv-python-headless`, `numpy`, `qrcode`.
After this, **no internet is needed**.

## 2. Run

```bash
python server.py
```

On Windows just double-click the **Draw to the Sky** shortcut on the desktop (or `start.bat`).
It starts the server and opens two browser tabs: the **QR page** and the **Sky page** (in front).
Clicking the shortcut again while it is running just opens the pages again.

The window prints something like:

```
  Big screen (sky):      http://localhost:3000/sky
  QR code for phones:    http://localhost:3000/connect
  Phone (same Wi-Fi):    http://192.168.1.23:3000/capture
```

On the Sky page press **F** for fullscreen.
The Sky page shows only the space background and the drawings, no buttons or QR code.

| Key on the Sky page | What it does |
|---|---|
| **F** | fullscreen on/off |
| **D** | delete mode: click a drawing to remove it, plus a "Remove all…" button |
| **Esc** | leave delete mode / close the confirm box |

The first time, **Windows Firewall** may ask whether Python may use the network.
Tick **Private networks** and click **Allow**.

## 3. Connect the phone

1. Connect the phone to the **same Wi-Fi** as the laptop.
2. Open `http://localhost:3000/connect` (in a second browser window, on a second screen, or on a
   tablet using the laptop's address) and scan the QR code with the phone camera. Or type the
   address shown under it into the phone (for example `192.168.1.23:3000/capture`).
3. The phone shows two buttons:
   - **Take a picture:** photograph the drawing, check the preview and tap **Send to the sky**.
     It appears on the big screen in about a second, glowing in one colour with little sparkling
     stars for a few seconds so the child can find it, then it stops glowing and floats.
   - **See the photos:** every drawing on the sky, newest first. Tap the red **×** on one to delete it,
     or **Delete all** at the bottom (it asks first).

If the cut-out is too strict (parts missing) move the **Sensitivity** slider to **More**.
If it picks up shadows or smudges, move it to **Less**. The slider setting is remembered on the phone.

Works with iPhone Safari and Android Chrome over plain `http://` (no HTTPS needed).

## 4. If the phone cannot open the page

Check these in order:

1. **Same network?** The phone must be on the same Wi-Fi as the laptop, not on mobile data.
2. **Firewall:** in Windows Settings → Network → Wi-Fi → your network, set the profile to **Private**.
   Or allow the port once from an *administrator* PowerShell:
   ```powershell
   netsh advfirewall firewall add rule name="Draw to the Sky" dir=in action=allow protocol=TCP localport=3000
   ```
3. **Wrong address?** If the server printed several "...or try:" addresses, try those.
4. **Wi-Fi client isolation** (common on school, hotel and guest Wi-Fi: devices can't see each other).
   Make your own network instead, see section 4b.

The QR page checks the network every few seconds, so after switching networks the QR code and
address update by themselves (no restart needed). Reload the page on the phone after switching.

## 4b. No Wi-Fi at all? Connect the phone directly

The app only needs the laptop and the phone to be on the **same small network**. No internet needed.
Any of these works (best first):

1. **Phone hotspot (works for iPhone and Android).** On the capture phone turn on **Personal Hotspot /
   Mobile hotspot**, then connect the **laptop** to that hotspot's Wi-Fi name. Open the QR page on the
   laptop and scan it with the same phone. The phone is both the network and the camera.
   - To avoid using mobile data: turn **mobile data off** on Android (the hotspot still works for the
     laptop–phone link). On iPhone the hotspot may need mobile data on. To be safe, in Windows set that
     hotspot connection to **Metered** (Settings → Network → Wi-Fi → the hotspot → Metered connection).
2. **USB cable (Android).** Plug the phone into the laptop, then on the phone: Settings → Network /
   Connections → Hotspot & tethering → **USB tethering** on. The QR page shows the new address
   (often `192.168.42.x`). No Wi-Fi involved at all.
3. **Laptop hotspot.** Windows Settings → Network & internet → **Mobile hotspot** → On, then connect the
   phone to it. Windows only allows this when the laptop has some connection to share (cable or Wi-Fi);
   if the switch is greyed out, use option 1 or 2.

**Firewall:** Windows may treat the new connection as *Public* and block the phone. Set the connection to
**Private** (Settings → Network → click it → Network profile type → Private), or run the `netsh` command
from section 4 once. It allows port 3000 on every network.

## 5. Clearing drawings

- **From the phone (easiest):** **See the photos** → red **×** on a drawing → **Delete**.
  Or **See the photos** → **Delete all** at the bottom → **Delete all**.
- **From the laptop:** on the Sky page press **D**, click a drawing to remove it, or use
  **Remove all…**; press **D** again to finish.
- Deleted drawings are not destroyed. They are moved to `drawings/_trash/`, so you can put them back
  by moving the PNGs into `drawings/`. Delete `drawings/_trash` yourself when you no longer need it.
- With the server stopped you can also just delete the PNG files in the `drawings/` folder.

**Delete PIN (optional):** by default any phone that opens the page on the same Wi-Fi can delete.
To stop guests doing that, set a PIN in `server.py`, e.g. `ADMIN_PIN = "4321"`, and restart the server.
The phone asks for it the first time you delete something and remembers it. The laptop never needs it.

All drawings are saved as PNG files in `drawings/` and survive a restart. Only the newest 60 are shown
at once; older ones gently fade out but stay on disk.

## 6. Changing colours, speeds and sizes

- **Look and motion:** the `CONFIG` block at the top of `static/sky.js` controls the background
  (moving or still, how fast), drift and spin speeds, drawing sizes, how long a new drawing glows
  and sparkles, the list of glow colours (`glowColors`: each new drawing gets one, taking turns),
  and the max number on screen. Save the file and reload the Sky page.
- **Background pictures:** the big screen uses `static/space.jpg`, the phone uses `static/phone_bg.jpg`.
  Replace either file (same name) to change it. A taller, higher-resolution picture looks sharper on phones.
- **Phone colours:** the black / green / red values are at the top of `static/capture.html` (`--black`, `--green`, `--red`).
- **Server:** the `CONFIG` block at the top of `server.py` sets the port, the default slider value,
  the delete PIN and the optional rembg mode.
- **Cut-out tuning:** the constants at the top of `imageproc.py` set the output size, the white
  "sticker" border, edge softness and colour boost.

## 7. Optional "better" cut-out (rembg) — off by default

The default cut-out uses classic image processing and needs no internet. If you want to try a
neural background-removal model:

```bash
pip install rembg onnxruntime
```

Then set `USE_REMBG = True` in `server.py`. The model (about 170 MB) downloads **the first time it is used**,
so run one test photo at home with internet before the event. If rembg is missing, the app falls
back to the classic mode automatically. For drawings on white paper the classic mode is usually as good.

## 8. Testing the cut-out yourself

```bash
python tools/make_test_images.py      # makes fake photos with shadows and tilt
python tools/test_pipeline.py         # checks them, writes tools/contact_sheet.png
python tools/test_pipeline.py my.jpg  # try your own photos
```

---

## Event-day checklist ✅

**The day before**
- [ ] `pip install -r requirements.txt` done, and `python server.py` starts without errors.
- [ ] Test at home: phone on the same Wi-Fi, scan the QR code, send one real drawing.
- [ ] Laptop charger, a spare phone charger or power bank, a few white A4 sheets, dark markers and crayons.

**At the venue (about 30 minutes before)**
- [ ] Laptop plugged in. Turn off sleep and screen-off (Settings → System → Power).
- [ ] Connect the laptop to the venue Wi-Fi **or** turn on the laptop's Mobile hotspot.
- [ ] No venue Wi-Fi? Turn on the phone's hotspot and connect the laptop to it (section 4b).
- [ ] Double-click the **Draw to the Sky** desktop shortcut and allow the firewall prompt (Private).
- [ ] Open `http://localhost:3000/sky` in Chrome or Edge, connect the projector or big screen, press **F**.
- [ ] Open `http://localhost:3000/connect` and scan the QR code with the helper phone. If it doesn't load, see section 4 and use a hotspot.
- [ ] Send one test drawing, then delete it on the phone (**See the photos** → **×**).
- [ ] Optional: **Delete all** on the phone to start with an empty sky.
- [ ] Phone: brightness up, auto-lock off or long, and add the page to the home screen if you like.

**Taking good photos**
- Good light, no strong shadow from your head or the phone; step to the side of the lamp.
- Hold the phone flat above the paper, with the whole drawing in the frame. Some table around the paper is fine.
- Dark marker or strong crayon colours work best. Very faint pencil: move the slider to **More**.

**After the event**
- Stop the server (close the window). All drawings are in the `drawings/` folder, so copy it if you want to keep them.
