"""
Run the cut-out pipeline on tools/test_images and check it against ground truth.

    python tools/make_test_images.py
    python tools/test_pipeline.py            -> prints IoU per image, writes tools/contact_sheet.png

You can also pass your own photos:  python tools/test_pipeline.py my_photo.jpg ...
(no ground truth -> only the contact sheet is produced)
"""
import glob
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import imageproc  # noqa: E402

HERE = os.path.dirname(__file__)
PASS_IOU = 0.85


def checker(h, w, s=16):
    yy, xx = np.mgrid[0:h, 0:w]
    c = (((yy // s) + (xx // s)) % 2).astype(np.uint8)
    out = np.where(c[..., None] == 1, 205, 245).astype(np.uint8)
    return np.repeat(out, 3, axis=2)


def space(h, w):
    yy = np.linspace(0, 1, h)[:, None, None]
    top = np.array([60, 20, 18], np.float32); bot = np.array([25, 8, 10], np.float32)
    out = (top * (1 - yy) + bot * yy) * np.ones((1, w, 1))
    r = np.random.default_rng(1)
    for _ in range(h * w // 900):
        out[r.integers(0, h), r.integers(0, w)] = 230
    return out.astype(np.uint8)


def over(bg, rgba):
    a = rgba[..., 3:4].astype(np.float32) / 255
    return (rgba[..., :3] * a + bg * (1 - a)).astype(np.uint8)


def fit(img, h):
    s = h / img.shape[0]
    return cv2.resize(img, (max(1, int(img.shape[1] * s)), h), interpolation=cv2.INTER_AREA)


def tile(img, w, h):
    t = np.full((h, w, 3), 255, np.uint8)
    f = fit(img, h)
    if f.shape[1] > w:
        f = cv2.resize(f, (w, int(f.shape[0] * w / f.shape[1])), interpolation=cv2.INTER_AREA)
    y = (h - f.shape[0]) // 2; x = (w - f.shape[1]) // 2
    t[y:y + f.shape[0], x:x + f.shape[1]] = f
    return t


def main(paths):
    rows = []
    failures = 0
    for p in paths:
        name = os.path.splitext(os.path.basename(p))[0]
        data = open(p, "rb").read()
        work = imageproc.prepare(data)
        truth_p = p.replace(".jpg", "_mask.png")
        truth = cv2.imread(truth_p, cv2.IMREAD_GRAYSCALE) if os.path.exists(truth_p) else None
        line = f"{name:28s}"
        results = {}
        for sens in (30, 50, 70):
            t0 = time.perf_counter()
            try:
                r = imageproc.cutout(work, sens, debug=True)
            except imageproc.NoDrawingFound:
                line += f"  s{sens}: NONE      "
                results[sens] = None
                continue
            ms = (time.perf_counter() - t0) * 1000
            results[sens] = r
            if truth is not None:
                tr = cv2.resize(truth, (work.shape[1], work.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
                pr = r["debug_mask"] > 0
                iou = (tr & pr).sum() / max(1, (tr | pr).sum())
                r["iou"] = iou
                line += f"  s{sens}: IoU {iou:.3f} {ms:4.0f}ms"
            else:
                line += f"  s{sens}: ok {ms:4.0f}ms"
        default = results.get(50)
        if truth is not None and (default is None or default["iou"] < PASS_IOU):
            failures += 1
            line += "   <-- FAIL"
        print(line)

        H = 260
        cells = [tile(work, 340, H)]
        for sens in (30, 50, 70):
            r = results[sens]
            if r is None:
                cells.append(np.full((H, 300, 3), 80, np.uint8))
                continue
            rgba = cv2.imdecode(np.frombuffer(r["png"], np.uint8), cv2.IMREAD_UNCHANGED)
            bgc = checker(*rgba.shape[:2]) if sens != 50 else space(*rgba.shape[:2])
            c = tile(over(bgc, rgba), 300, H)
            cv2.putText(c, f"s{sens}" + (f" IoU {r['iou']:.2f}" if "iou" in r else ""), (6, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 200), 2)
            cells.append(c)
        row = np.hstack([np.pad(c, ((4, 4), (4, 4), (0, 0)), constant_values=255) for c in cells])
        rows.append(row)
    sheet = np.vstack(rows)
    out = os.path.join(HERE, "contact_sheet.png")
    cv2.imwrite(out, sheet)
    print("contact sheet:", out)
    print("FAILURES:", failures)
    return failures


if __name__ == "__main__":
    args = sys.argv[1:] or sorted(p for p in glob.glob(os.path.join(HERE, "test_images", "*.jpg")))
    sys.exit(1 if main(args) else 0)
