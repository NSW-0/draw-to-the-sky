"""
Generate fake "phone photos" of kids' drawings for testing the cut-out pipeline.

Each case: drawing on off-white paper -> paper placed on a table, camera tilted
(perspective), uneven light, a cast shadow, noise, JPEG artefacts.
Also writes the ground-truth mask (filled silhouette) in photo coordinates.

    python tools/make_test_images.py        -> tools/test_images/*.jpg + *_mask.png
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from imageproc import fill_holes  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "test_images")
PW, PH = 1400, 1000          # paper canvas (landscape)
rng = np.random.default_rng(7)


# ------------------------------------------------------------ drawing kit ----
class Sheet:
    def __init__(self, tint=(246, 248, 250)):
        self.img = np.zeros((PH, PW, 3), np.uint8)
        self.img[:] = tint
        # paper grain
        grain = rng.normal(0, 2.0, (PH, PW, 1)).astype(np.float32)
        self.img = np.clip(self.img.astype(np.float32) + grain, 0, 255).astype(np.uint8)
        self.truth = np.zeros((PH, PW), np.uint8)

    def _paint(self, shape_mask, color, crayon):
        if crayon:
            # stroke-like texture with paper gaps
            n = rng.random((PH, PW)).astype(np.float32)
            n = cv2.GaussianBlur(n, (0, 0), 1.2)
            ang = rng.uniform(0, 180)
            k = np.zeros((15, 15), np.float32); k[7, :] = 1
            k = cv2.warpAffine(k, cv2.getRotationMatrix2D((7, 7), ang, 1), (15, 15))
            n = cv2.filter2D(n, -1, k / k.sum())
            n = (n - n.mean()) / (n.std() + 1e-6)
            cover = (n > -0.45)  # ~70% coverage
            m = (shape_mask > 0) & cover
            shade = rng.uniform(0.85, 1.0, (PH, PW, 1))
            col = np.clip(np.array(color, np.float32) * shade, 0, 255)
            self.img[m] = (0.15 * self.img[m] + 0.85 * col[m]).astype(np.uint8)
        else:
            self.img[shape_mask > 0] = color
        self.truth |= shape_mask

    def fill_poly(self, pts, color, crayon=True):
        m = np.zeros((PH, PW), np.uint8)
        cv2.fillPoly(m, [np.int32(pts)], 255, cv2.LINE_AA)
        self._paint((m > 127).astype(np.uint8) * 255, color, crayon)

    def circle(self, c, r, color, crayon=True, thickness=-1):
        m = np.zeros((PH, PW), np.uint8)
        cv2.circle(m, c, r, 255, thickness, cv2.LINE_AA)
        self._paint((m > 127).astype(np.uint8) * 255, color, crayon)

    def ellipse(self, c, axes, ang, color, thickness, crayon=False):
        m = np.zeros((PH, PW), np.uint8)
        cv2.ellipse(m, c, axes, ang, 0, 360, 255, thickness, cv2.LINE_AA)
        self._paint((m > 127).astype(np.uint8) * 255, color, crayon)

    def lines(self, pts, color, thickness, closed=True):
        m = np.zeros((PH, PW), np.uint8)
        cv2.polylines(m, [np.int32(pts)], closed, 255, thickness, cv2.LINE_AA)
        self._paint((m > 127).astype(np.uint8) * 255, color, False)


def star_pts(cx, cy, r1, r2, n=5, rot=-90):
    pts = []
    for i in range(2 * n):
        r = r1 if i % 2 == 0 else r2
        a = np.radians(rot + i * 180 / n)
        pts.append((cx + r * np.cos(a), cy + r * np.sin(a)))
    return np.array(pts)


# BGR colours
ORANGE = (40, 140, 245); YELLOW = (40, 215, 250); RED = (40, 40, 220)
DBLUE = (120, 40, 20); GREEN = (60, 180, 60); PURPLE = (160, 60, 130)
BLACK = (35, 30, 30); GREY = (120, 120, 120); BLUE = (200, 120, 40)


def case_planet():
    s = Sheet()
    s.circle((700, 500), 230, ORANGE)
    s.ellipse((700, 500), (380, 90), -15, DBLUE, 22)
    s.circle((700, 500), 230, BLACK, crayon=False, thickness=6)
    return s


def case_yellow_star():
    s = Sheet()
    s.fill_poly(star_pts(700, 520, 330, 140), YELLOW)
    return s


def case_rocket():
    s = Sheet()
    body = np.array([(700, 150), (790, 300), (790, 650), (610, 650), (610, 300)])
    s.lines(body, DBLUE, 9)
    s.lines(np.array([(610, 520), (520, 690), (610, 650)]), DBLUE, 9)
    s.lines(np.array([(790, 520), (880, 690), (790, 650)]), DBLUE, 9)
    s.circle((700, 380), 50, DBLUE, crayon=False, thickness=8)
    s.fill_poly(np.array([(630, 660), (770, 660), (735, 800), (700, 880), (665, 800)]), RED)
    s.fill_poly(np.array([(665, 665), (735, 665), (715, 770), (700, 810), (685, 770)]), YELLOW)
    return s


def case_alien():
    s = Sheet()
    s.fill_poly(cv2.ellipse2Poly((700, 560), (210, 260), 0, 0, 360, 5), GREEN)
    s.lines(np.array([(620, 330), (560, 180)]), BLACK, 7, closed=False)
    s.lines(np.array([(780, 330), (840, 180)]), BLACK, 7, closed=False)
    s.circle((560, 175), 24, PURPLE)
    s.circle((840, 175), 24, PURPLE)
    s.circle((630, 520), 40, (250, 250, 250), crayon=False)
    s.circle((770, 520), 40, (250, 250, 250), crayon=False)
    s.circle((630, 520), 16, BLACK, crayon=False)
    s.circle((770, 520), 16, BLACK, crayon=False)
    # three little separate stars next to it
    for (x, y) in [(330, 300), (1060, 380), (1000, 800)]:
        s.fill_poly(star_pts(x, y, 45, 20), YELLOW)
    return s


def case_small_moon():
    s = Sheet()
    m = np.zeros((PH, PW), np.uint8)
    cv2.circle(m, (700, 500), 120, 255, -1)
    cv2.circle(m, (760, 460), 110, 0, -1)
    s._paint(m, GREY, True)
    return s


def case_pencil_planet():
    s = Sheet()
    s.circle((700, 500), 260, (110, 105, 100), crayon=False, thickness=4)
    s.ellipse((700, 500), (420, 80), 10, (110, 105, 100), 4)
    return s


def case_full_frame():
    s = Sheet((238, 244, 248))
    s.circle((520, 480), 250, BLUE)
    s.circle((520, 480), 250, BLACK, crayon=False, thickness=5)
    s.fill_poly(star_pts(1050, 300, 120, 50), YELLOW)
    s.fill_poly(star_pts(1080, 720, 90, 38), ORANGE)
    return s


def case_purple_planet_dark_table():
    s = Sheet()
    s.circle((700, 500), 300, PURPLE)
    s.circle((620, 420), 60, (200, 150, 230))
    return s


def case_solid_marker_planet():
    """Big areas filled solid with marker (no paper showing through)."""
    s = Sheet()
    s.circle((700, 500), 330, ORANGE, crayon=False)
    s.circle((700, 500), 330, BLACK, crayon=False, thickness=8)
    s.fill_poly(star_pts(1180, 220, 110, 45), YELLOW, crayon=False)
    return s


def case_faint_pencil_star():
    s = Sheet()
    s.lines(star_pts(700, 520, 320, 130), (175, 172, 168), 3)
    return s


def case_dusty_paper():
    """Rocket in marker + dust specks, a faint eraser smudge (not drawing)."""
    s = case_rocket()
    for _ in range(40):  # dust / crumbs: tiny dots, should be removed
        x, y = int(rng.uniform(80, PW - 80)), int(rng.uniform(80, PH - 80))
        cv2.circle(s.img, (x, y), int(rng.integers(1, 3)), (90, 90, 90), -1)
    sm = np.zeros((PH, PW), np.float32)
    cv2.ellipse(sm, (300, 750), (130, 50), 20, 0, 360, 1.0, -1)
    sm = cv2.GaussianBlur(sm, (0, 0), 25)
    s.img = (s.img * (1 - 0.10 * sm[..., None])).astype(np.uint8)
    return s


# ------------------------------------------------------------ "camera" -------
def table(w, h, kind):
    if kind == "wood":
        base = np.zeros((h, w, 3), np.float32); base[:] = (60, 105, 150)
        streak = rng.normal(0, 1, (h, 1)).astype(np.float32)
        streak = cv2.GaussianBlur(streak, (0, 0), 3)
        streak = np.repeat(streak, w, axis=1)[..., None] * 18
        return np.clip(base + streak + rng.normal(0, 4, (h, w, 1)), 0, 255)
    if kind == "dark":
        base = np.zeros((h, w, 3), np.float32); base[:] = (55, 52, 50)
        return np.clip(base + rng.normal(0, 4, (h, w, 1)), 0, 255)
    base = np.zeros((h, w, 3), np.float32); base[:] = (150, 150, 145)   # grey desk
    return np.clip(base + rng.normal(0, 3, (h, w, 1)), 0, 255)


def photograph(sheet, kind="wood", tilt=0.10, cover=0.78, full_frame=False, shadow=0.45, name=""):
    W, H = 1600, 1200
    if full_frame:
        # camera so close the paper fills the photo (crop the middle of the sheet)
        src = np.float32([[60, 40], [PW - 60, 40], [PW - 60, PH - 40], [60, PH - 40]])
        dst = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
        jitter = rng.uniform(-tilt, tilt, (4, 2)) * 400
        src = (src + jitter).astype(np.float32)
        M = cv2.getPerspectiveTransform(src, dst)
        photo = cv2.warpPerspective(sheet.img, M, (W, H), borderMode=cv2.BORDER_REFLECT).astype(np.float32)
        truth = cv2.warpPerspective(sheet.truth, M, (W, H), flags=cv2.INTER_NEAREST)
    else:
        pw = W * cover; ph = pw * PH / PW
        cx, cy = W / 2 + rng.uniform(-60, 60), H / 2 + rng.uniform(-40, 40)
        dst = np.float32([[cx - pw / 2, cy - ph / 2], [cx + pw / 2, cy - ph / 2],
                          [cx + pw / 2, cy + ph / 2], [cx - pw / 2, cy + ph / 2]])
        # keystone (tilted camera): top edge narrower, plus a small rotation
        dst[0, 0] += pw * tilt; dst[1, 0] -= pw * tilt
        ang = np.radians(rng.uniform(-6, 6))
        R = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
        dst = ((dst - [cx, cy]) @ R.T + [cx, cy]).astype(np.float32)
        src = np.float32([[0, 0], [PW, 0], [PW, PH], [0, PH]])
        M = cv2.getPerspectiveTransform(src, dst)
        bg = table(W, H, kind)
        warped = cv2.warpPerspective(sheet.img, M, (W, H)).astype(np.float32)
        pm = cv2.warpPerspective(np.full((PH, PW), 255, np.uint8), M, (W, H))
        pm = cv2.GaussianBlur(pm.astype(np.float32) / 255, (0, 0), 0.8)[..., None]
        photo = warped * pm + bg * (1 - pm)
        truth = cv2.warpPerspective(sheet.truth, M, (W, H), flags=cv2.INTER_NEAREST)

    # uneven light: gradient + vignette
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    g = 0.78 + 0.25 * (xx / W) * 0.6 + 0.25 * (1 - yy / H) * 0.4
    vig = 1 - 0.25 * (((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2) * 2
    photo *= (g * vig)[..., None]
    # warm indoor light tint
    photo *= np.array([0.93, 0.98, 1.03], np.float32)
    # cast shadow (phone / hand) on one corner
    if shadow > 0:
        sm = np.zeros((H, W), np.float32)
        poly = np.int32([[W * 0.55, -50], [W + 50, -50], [W + 50, H * 0.55], [W * 0.82, H * 0.35]])
        cv2.fillPoly(sm, [poly], 1.0)
        sm = cv2.GaussianBlur(sm, (0, 0), 45)
        photo *= (1 - shadow * sm)[..., None]
    photo += rng.normal(0, 3.0, photo.shape)
    photo = np.clip(photo, 0, 255).astype(np.uint8)
    truth = fill_holes((truth > 0).astype(np.uint8) * 255)

    os.makedirs(OUT, exist_ok=True)
    cv2.imwrite(os.path.join(OUT, f"{name}.jpg"), photo, [cv2.IMWRITE_JPEG_QUALITY, 82])
    cv2.imwrite(os.path.join(OUT, f"{name}_mask.png"), truth)


CASES = [
    ("01_planet_wood", case_planet, dict(kind="wood", tilt=0.10)),
    ("02_yellow_star_grey", case_yellow_star, dict(kind="grey", tilt=0.08)),
    ("03_rocket_outline", case_rocket, dict(kind="wood", tilt=0.12)),
    ("04_alien_pieces", case_alien, dict(kind="grey", tilt=0.06, shadow=0.55)),
    ("05_small_moon", case_small_moon, dict(kind="wood", tilt=0.09, cover=0.7)),
    ("06_pencil_planet", case_pencil_planet, dict(kind="grey", tilt=0.07)),
    ("07_full_frame_shadow", case_full_frame, dict(full_frame=True, tilt=0.05, shadow=0.5)),
    ("08_purple_dark_table", case_purple_planet_dark_table, dict(kind="dark", tilt=0.12)),
    ("09_faint_pencil_star", case_faint_pencil_star, dict(kind="wood", tilt=0.08)),
    ("10_dusty_paper", case_dusty_paper, dict(kind="grey", tilt=0.10, shadow=0.5)),
    ("11_solid_marker_planet", case_solid_marker_planet, dict(kind="wood", tilt=0.08, shadow=0.5)),
]

if __name__ == "__main__":
    for name, fn, kw in CASES:
        photograph(fn(), name=name, **kw)
        print("wrote", name)
