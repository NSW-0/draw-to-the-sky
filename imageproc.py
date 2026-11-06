"""
Cut a kid's drawing out of a phone photo of white/light paper.

Classic, offline image processing (OpenCV + NumPy). No internet, no models.
Optional "better" mode with rembg can be switched on in server.py (USE_REMBG).

Pipeline:
  1. resize to ~1000 px long side
  2. find the sheet of paper; if it is a clear 4-corner shape, un-tilt it
  3. even out lighting/shadows (divide by an estimate of the empty paper)
  4. mask = pixels whose colour differs from the paper colour
  5. clean: close/open, fill holes, keep main components, drop specks
  6. soften the edge, make paper transparent, crop with a small margin
  7. transparent PNG, <= ~600 px long side
"""

import cv2
import numpy as np

# ---------------------------------------------------------------- tunables ---
WORK_LONG_SIDE = 1000      # px, photo is resized to this before processing
OUTPUT_LONG_SIDE = 600     # px, max size of the saved PNG
CROP_MARGIN = 14           # px (in work resolution) around the drawing
STICKER_BORDER = 3         # px of white paper kept around strokes ("sticker" rim)
EDGE_SOFTNESS = 1.3        # Gaussian sigma for the soft alpha edge
SATURATION_BOOST = 1.20    # make crayon colours a bit punchier on screen
# Sensitivity 0..100 maps to a colour-difference threshold (higher = keeps more)
THRESH_AT_0 = 46.0
THRESH_AT_100 = 12.0
MIN_SPECK_FRACTION = 0.0003   # components smaller than this * image area are removed
MAIN_FRACTION = 0.02          # components >= this * largest are always kept
NEAR_DISTANCE = 0.12          # smaller pieces kept only if this close (* long side) to main
EDGE_HIGH_AT_0 = 110.0        # Canny high threshold at sensitivity 0 (low = 1/3 of it)
EDGE_HIGH_AT_100 = 24.0       # ... at sensitivity 100 (fainter edges count as drawing)
COLOR_ALWAYS = 30.0           # this colourful (vs the paper) always counts as drawing, even without sharp edges
# -----------------------------------------------------------------------------


class NoDrawingFound(Exception):
    pass


def decode_image(data: bytes):
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # applies EXIF orientation
    if img is None:
        raise ValueError("Could not read the image")
    return img


def resize_long(img, long_side, interp=cv2.INTER_AREA):
    h, w = img.shape[:2]
    s = long_side / max(h, w)
    if abs(s - 1) < 1e-3:
        return img
    return cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s))),
                      interpolation=interp if s < 1 else cv2.INTER_CUBIC)


def sensitivity_to_threshold(sensitivity):
    s = min(100.0, max(0.0, float(sensitivity))) / 100.0
    return THRESH_AT_0 + (THRESH_AT_100 - THRESH_AT_0) * s


# ----------------------------------------------------------------- paper -----
def _order_quad(pts):
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)  # tl tr br bl


def find_paper(img):
    """Return (paper_mask uint8 0/255, quad or None)."""
    h, w = img.shape[:2]
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[..., 0]
    chroma = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    score = cv2.GaussianBlur(L - 1.5 * chroma, (0, 0), 4)
    score = cv2.normalize(score, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    _, bright = cv2.threshold(score, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN, k)

    contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    full = np.full((h, w), 255, np.uint8)
    if not contours:
        return full, None
    c = max(contours, key=cv2.contourArea)
    area_frac = cv2.contourArea(c) / (h * w)
    if area_frac < 0.15:          # nothing paper-like: use the whole photo
        return full, None
    hull = cv2.convexHull(c)
    paper = np.zeros((h, w), np.uint8)
    cv2.drawContours(paper, [hull], -1, 255, -1)

    # How much of the photo border is "not paper"? If almost none, paper fills frame.
    border = np.concatenate([paper[0], paper[-1], paper[:, 0], paper[:, -1]])
    if (border > 0).mean() > 0.97:
        return full, None

    peri = cv2.arcLength(hull, True)
    for eps in (0.015, 0.02, 0.03, 0.04):
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4:
            quad = _order_quad(approx)
            qa = cv2.contourArea(quad) / (h * w)
            if 0.15 < qa < 0.98:
                return paper, quad
            break
    # Not a clean quad (e.g. paper runs off the photo): use the region, shrunk a bit
    paper = cv2.erode(paper, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    return paper, None


def warp_paper(img, quad):
    tl, tr, br, bl = quad
    wdt = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    hgt = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    dst = np.array([[0, 0], [wdt - 1, 0], [wdt - 1, hgt - 1], [0, hgt - 1]], np.float32)
    M = cv2.getPerspectiveTransform(quad, dst)
    out = cv2.warpPerspective(img, M, (wdt, hgt), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE)
    return out, M


# -------------------------------------------------------------- lighting -----
def edge_support(img, roi, sensitivity=50):
    """
    Regions bounded by SHARP colour edges. Marker/crayon drawings have sharp
    edges; shadows and lighting gradients are soft, so they are excluded.
    """
    s = min(100.0, max(0.0, float(sensitivity))) / 100.0
    hi = EDGE_HIGH_AT_0 + (EDGE_HIGH_AT_100 - EDGE_HIGH_AT_0) * s
    blur = cv2.GaussianBlur(img, (0, 0), 1.2)
    edges = np.zeros(img.shape[:2], np.uint8)
    for ch in cv2.split(blur):
        edges |= cv2.Canny(ch, hi / 3, hi)
    edges &= roi
    edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    return fill_holes(edges)


def _lab_distance(img_u8, ref_lab):
    lab = cv2.cvtColor(img_u8, cv2.COLOR_BGR2LAB).astype(np.float32)
    dL = lab[..., 0] - ref_lab[0]
    da = (lab[..., 1] - ref_lab[1]) * 1.4
    db = (lab[..., 2] - ref_lab[2]) * 1.4
    # only darker-than-paper counts for L (bright glare is not ink)
    dL = np.minimum(dL, 0)
    return np.sqrt(dL * dL + da * da + db * db)


def _paper_ref(img_u8, paper_bool):
    lab = cv2.cvtColor(img_u8, cv2.COLOR_BGR2LAB).reshape(-1, 3)
    sel = lab[paper_bool.ravel()]
    if len(sel) < 100:
        sel = lab
    return np.median(sel, axis=0).astype(np.float32)


def normalize_lighting(img, roi, support):
    """Divide the photo by a smooth estimate of the blank paper -> paper ~ white."""
    h, w = img.shape[:2]
    f = img.astype(np.float32) + 1.0
    sc = 0.25
    small = cv2.resize(f, (max(8, int(w * sc)), max(8, int(h * sc))), interpolation=cv2.INTER_AREA)
    size_s = (small.shape[1], small.shape[0])
    roi_s = cv2.resize(roi, size_s, interpolation=cv2.INTER_NEAREST) > 0
    sup_s = cv2.resize(support, size_s, interpolation=cv2.INTER_AREA) > 0

    # pass 1: max-filter removes thin dark strokes, blur gives rough paper estimate
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
    bg1 = cv2.GaussianBlur(cv2.dilate(small, k), (0, 0), 6)
    norm1 = np.clip(small / bg1 * 255, 0, 255).astype(np.uint8)
    ref1 = _paper_ref(norm1, roi_s)
    # Everything enclosed by sharp drawing edges is "not paper", even if it looks
    # uniform (a big solid marker fill would otherwise be mistaken for paper and
    # turn white). Soft shadows have no sharp edges, so they still count as paper.
    ink1 = (((_lab_distance(norm1, ref1) > 14) & sup_s) | sup_s).astype(np.uint8)
    ink1 = cv2.dilate(ink1, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    paper_w = ((ink1 == 0) & roi_s).astype(np.float32)

    # pass 2: normalized convolution over paper-only pixels (robust under big filled shapes)
    def nconv(sigma):
        num = cv2.GaussianBlur(small * paper_w[..., None], (0, 0), sigma)
        den = cv2.GaussianBlur(paper_w, (0, 0), sigma)
        return num, den

    num_s, den_s = nconv(8)
    num_l, den_l = nconv(30)
    if paper_w.sum() > 50:
        glob = (small * paper_w[..., None]).reshape(-1, 3).sum(0) / paper_w.sum()
    else:
        glob = np.array([240, 240, 240], np.float32)
    bg_l = np.where(den_l[..., None] > 1e-3, num_l / np.maximum(den_l, 1e-6)[..., None], glob)
    c = 0.03
    bg = (num_s + c * bg_l) / (den_s[..., None] + c)
    bg = cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR)
    norm = np.clip(f / np.maximum(bg, 1.0) * 255.0, 0, 255).astype(np.uint8)
    return norm


# ------------------------------------------------------------------- mask ----
def fill_holes(mask):
    h, w = mask.shape
    pad = cv2.copyMakeBorder(mask, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    ff = pad.copy()
    cv2.floodFill(ff, np.zeros((h + 4, w + 4), np.uint8), (0, 0), 255)
    holes = cv2.bitwise_not(ff)[1:-1, 1:-1]
    return cv2.bitwise_or(mask, holes)


def keep_main_components(mask):
    h, w = mask.shape
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return mask
    areas = stats[1:, cv2.CC_STAT_AREA]
    largest = areas.max()
    min_area = MIN_SPECK_FRACTION * h * w
    main = [i + 1 for i, a in enumerate(areas) if a >= MAIN_FRACTION * largest]
    keep = np.zeros(n, bool)
    keep[main] = True
    # bounding box of the main pieces
    xs0 = min(stats[i, 0] for i in main); ys0 = min(stats[i, 1] for i in main)
    xs1 = max(stats[i, 0] + stats[i, 2] for i in main); ys1 = max(stats[i, 1] + stats[i, 3] for i in main)
    near = NEAR_DISTANCE * max(h, w)
    for i in range(1, n):
        if keep[i] or stats[i, cv2.CC_STAT_AREA] < min_area:
            continue
        x, y, bw, bh = stats[i, :4]
        dx = max(xs0 - (x + bw), x - xs1, 0)
        dy = max(ys0 - (y + bh), y - ys1, 0)
        if np.hypot(dx, dy) <= near:
            keep[i] = True
    return (keep[lab] * 255).astype(np.uint8)


def _chroma_distance(img_u8, ref_lab):
    lab = cv2.cvtColor(img_u8, cv2.COLOR_BGR2LAB).astype(np.float32)
    return np.hypot(lab[..., 1] - ref_lab[1], lab[..., 2] - ref_lab[2]) * 1.4


def build_mask(norm, roi, support, threshold):
    paper_bool = roi > 0
    ref = _paper_ref(norm, paper_bool & (support == 0))
    dist = cv2.GaussianBlur(_lab_distance(norm, ref), (0, 0), 1.0)
    chroma = cv2.GaussianBlur(_chroma_distance(norm, ref), (0, 0), 1.0)
    # Drawing = different from the paper AND (inside sharp edges OR clearly coloured).
    # Shadows only darken grey paper (no colour change, no sharp edge), so they stay out.
    likely = (support > 0) | (chroma > max(threshold, COLOR_ALWAYS))
    mask = ((dist > threshold) & paper_bool & likely).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    mask = fill_holes(mask)
    mask = keep_main_components(mask)
    return mask


# --------------------------------------------------------------- optional ----
_rembg_session = None


def rembg_mask(img_bgr):
    """Return a 0/255 mask from rembg, or None if rembg is not installed."""
    global _rembg_session
    try:
        from rembg import remove, new_session
    except Exception:
        return None
    if _rembg_session is None:
        _rembg_session = new_session("u2net")
    ok, buf = cv2.imencode(".png", img_bgr)
    out = remove(buf.tobytes(), session=_rembg_session)
    rgba = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_UNCHANGED)
    if rgba is None or rgba.shape[2] != 4:
        return None
    return ((rgba[..., 3] > 128) * 255).astype(np.uint8)


# ------------------------------------------------------------------- main ----
def prepare(data: bytes):
    """Decode + resize once (cached by the server while the slider moves)."""
    return resize_long(decode_image(data), WORK_LONG_SIDE)


def cutout(work_img, sensitivity=50, use_rembg=False, debug=False):
    """
    work_img: BGR image already resized by prepare().
    Returns dict(png=bytes, size=(w,h), coverage=float[, debug_mask=mask in work_img coords]).
    Raises NoDrawingFound.
    """
    img = work_img
    h0, w0 = img.shape[:2]
    roi, quad = find_paper(img)
    M = None
    if quad is not None:
        img, M = warp_paper(img, quad)
        h, w = img.shape[:2]
        roi = np.zeros((h, w), np.uint8)
        inset = max(4, int(0.015 * max(h, w)))   # skip the paper's own edge
        roi[inset:h - inset, inset:w - inset] = 255
    support = edge_support(img, roi, sensitivity)
    norm = normalize_lighting(img, roi, support)

    mask = None
    if use_rembg:
        mask = rembg_mask(norm)
        if mask is not None:
            mask = cv2.bitwise_and(fill_holes(mask), roi)
    if mask is None:
        mask = build_mask(norm, roi, support, sensitivity_to_threshold(sensitivity))

    h, w = mask.shape
    coverage = float((mask > 0).sum()) / float(max(1, (roi > 0).sum()))
    if (mask > 0).sum() < 0.0015 * h * w:
        raise NoDrawingFound()

    # soft edge + white sticker rim
    if STICKER_BORDER > 0:
        b = 2 * STICKER_BORDER + 1
        grown = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (b, b)))
    else:
        grown = mask
    alpha = cv2.GaussianBlur(grown.astype(np.float32) / 255.0, (0, 0), EDGE_SOFTNESS)

    # colours: lighting-corrected, slightly more saturated
    hsv = cv2.cvtColor(norm, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * SATURATION_BOOST, 0, 255)
    color = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    ys, xs = np.where(alpha > 0.02)
    x0 = max(0, xs.min() - CROP_MARGIN); x1 = min(w, xs.max() + 1 + CROP_MARGIN)
    y0 = max(0, ys.min() - CROP_MARGIN); y1 = min(h, ys.max() + 1 + CROP_MARGIN)
    a8 = (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
    rgba = np.dstack([color, a8])[y0:y1, x0:x1]
    # pad so the soft edge never touches the PNG border
    rgba = cv2.copyMakeBorder(rgba, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
    if max(rgba.shape[:2]) > OUTPUT_LONG_SIDE:
        rgba = resize_long(rgba, OUTPUT_LONG_SIDE)
    ok, buf = cv2.imencode(".png", rgba, [cv2.IMWRITE_PNG_COMPRESSION, 6])
    result = {"png": buf.tobytes(), "size": (rgba.shape[1], rgba.shape[0]), "coverage": coverage}

    if debug:
        if M is not None:
            back = cv2.warpPerspective(mask, M, (w0, h0), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_NEAREST)
        else:
            back = mask
        result["debug_mask"] = back
    return result


def process_bytes(data: bytes, sensitivity=50, use_rembg=False):
    return cutout(prepare(data), sensitivity, use_rembg)
