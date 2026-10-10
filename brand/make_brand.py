"""Build ClaimScout's vector logo from the original artwork (brand/source/logo-original.png).

- Traces the dog and the wordmark with potrace into clean SVG paths.
- Mirrors the left half of the face so both eyes and the jaw match.
- Redraws the crosshair as exact geometry and cuts a gap around it out of the dog (no overlap with the ear),
  so every version works on any background and as a one-colour (themed / notification) icon.

Writes brand/*.svg, the Android vector drawables and the dashboard's inline logo.
Run: server/.venv/bin/python brand/make_brand.py   (needs: pip install pillow numpy potracer)
"""
from pathlib import Path

import numpy as np
import potrace
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "brand/source/logo-original.png"
OUT = ROOT / "brand"
RES = ROOT / "android/app/src/main/res"

BLUE = "#0081FE"      # sampled from the original
INK = "#191A1C"       # sampled from the original
LIGHT_INK = "#F2F3F5"  # outlines on dark backgrounds

S = 2                 # trace at 2x for smoother curves
AXIS = 626            # face centre line in the original (nose and ears are symmetric about it)
CX, CY = 751, 446     # crosshair centre in the original
R_OUT, R_IN = 110, 88  # ring
T_IN, T_OUT, T_W = 79, 132, 22  # ticks: from radius, to radius, width
GAP = 12              # white space kept around the crosshair
DOG_BOTTOM = 845      # the wordmark starts below this


def load():
    im = Image.open(SRC).convert("RGB")
    im = im.resize((im.width * S, im.height * S), Image.LANCZOS)
    a = np.asarray(im).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    blue = (b > 170) & (b - r > 90)
    dark = ((r + g + b) / 3 < 128) & ~blue
    return dark, blue


def crosshair_mask(shape, grow=0.0):
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    dx, dy = xx / S - CX, yy / S - CY
    d = np.hypot(dx, dy)
    ring = (d <= R_OUT + grow) & (d >= R_IN - grow)
    half = T_W / 2 + grow
    ticks = ((np.abs(dy) <= half) & (np.abs(dx) >= T_IN - grow) & (np.abs(dx) <= T_OUT + grow)) | \
            ((np.abs(dx) <= half) & (np.abs(dy) >= T_IN - grow) & (np.abs(dy) <= T_OUT + grow))
    return ring | ticks


def _grow(m, n):
    for _ in range(n):
        m = m | np.roll(m, 1, 0) | np.roll(m, -1, 0) | np.roll(m, 1, 1) | np.roll(m, -1, 1)
    return m


def face(dog, cross):
    """A white "sticker" under the whole dog: its outline with the thin gaps (ear/head) closed, plus a 12px
    border, so the black ears and outline stay visible on dark backgrounds."""
    from PIL import ImageDraw
    n = 14 * S   # closes gaps up to ~28px in the original
    walls = Image.fromarray(np.where(_grow(dog | cross, n), 0, 255).astype(np.uint8)).copy()  # writable copy
    ImageDraw.floodfill(walls, (0, 0), 128)
    outside = np.asarray(walls) == 128
    return ~_grow(outside, n - 12 * S)


def trace(mask, ox=0.0, oy=0.0, scale=1.0) -> str:
    """potrace a boolean mask into one SVG path (absolute commands; holes via even-odd)."""
    bm = potrace.Bitmap(~mask)   # potracer traces the False pixels
    plist = bm.trace(turdsize=8, alphamax=1.0, opticurve=True, opttolerance=0.2)
    f = lambda p: f"{(p.x / S - ox) * scale:.2f} {(p.y / S - oy) * scale:.2f}"
    out = []
    for curve in plist:
        out.append("M" + f(curve.start_point))
        for seg in curve.segments:
            if seg.is_corner:
                out.append("L" + f(seg.c) + "L" + f(seg.end_point))
            else:
                out.append("C" + f(seg.c1) + " " + f(seg.c2) + " " + f(seg.end_point))
        out.append("Z")
    return "".join(out)


def crosshair_path(ox=0.0, oy=0.0, scale=1.0) -> str:
    """Ring (two circles, even-odd) plus four tick bars, in absolute coordinates."""
    cx, cy = (CX - ox) * scale, (CY - oy) * scale
    ro, ri = R_OUT * scale, R_IN * scale
    p = []
    for rr in (ro, ri):
        p.append(f"M{cx - rr:.2f} {cy:.2f}A{rr:.2f} {rr:.2f} 0 1 0 {cx + rr:.2f} {cy:.2f}"
                 f"A{rr:.2f} {rr:.2f} 0 1 0 {cx - rr:.2f} {cy:.2f}Z")
    h, a, b = T_W / 2 * scale, T_IN * scale, T_OUT * scale
    # ticks overlap the ring; draw them as separate subpaths outside the ring and inside it
    for x0, x1 in ((-b, -ro), (ro, b), (-ri, -a), (a, ri)):
        p.append(f"M{cx + x0:.2f} {cy - h:.2f}H{cx + x1:.2f}V{cy + h:.2f}H{cx + x0:.2f}Z")
    for y0, y1 in ((-b, -ro), (ro, b), (-ri, -a), (a, ri)):
        p.append(f"M{cx - h:.2f} {cy + y0:.2f}H{cx + h:.2f}V{cy + y1:.2f}H{cx - h:.2f}Z")
    return "".join(p)


def main():
    dark, blue = load()
    h, w = dark.shape
    # dog: mirror the left half onto the right
    dog = dark[: DOG_BOTTOM * S].copy()
    left = dog[:, : AXIS * S + 1]
    right = left[:, ::-1][:, 1:]
    dog = np.concatenate([left, right], axis=1)[:, :w]
    if dog.shape[1] < w:
        dog = np.pad(dog, ((0, 0), (0, w - dog.shape[1])))
    # face fill uses the outline before the gap is cut, with the gap itself as a wall, so it can't leak out
    under = face(dog, crosshair_mask(dog.shape, grow=GAP))
    dog &= ~crosshair_mask(dog.shape, grow=GAP)
    word_ink = dark.copy(); word_ink[: DOG_BOTTOM * S] = False
    word_blue = blue.copy(); word_blue[: DOG_BOTTOM * S] = False

    # bounding boxes (original pixel units)
    DOG_BOX = (196, 196, 1057, 851)     # x0 y0 x1 y1, a little margin around ears and crosshair
    FULL_BOX = (60, 150, 1200, 1060)

    dog_p, face_p = trace(dog), trace(under)
    cross_p = crosshair_path()
    wi_p, wb_p = trace(word_ink), trace(word_blue)

    def svg(box, parts, bg=None):
        x0, y0, x1, y1 = box
        body = "".join(f'<path fill="{c}" fill-rule="evenodd" d="{d}"/>' for c, d in parts)
        rect = f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="{bg}"/>' if bg else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {x1 - x0} {y1 - y0}">'
                f"{rect}{body}</svg>\n")

    files = {
        "logo.svg": svg(FULL_BOX, [(INK, dog_p), (BLUE, cross_p), (INK, wi_p), (BLUE, wb_p)]),
        "logo-dark.svg": svg(FULL_BOX, [("#FFFFFF", face_p), (INK, dog_p), (BLUE, cross_p), (LIGHT_INK, wi_p), (BLUE, wb_p)]),
        "mark.svg": svg(DOG_BOX, [(INK, dog_p), (BLUE, cross_p)]),
        "mark-dark.svg": svg(DOG_BOX, [("#FFFFFF", face_p), (INK, dog_p), (BLUE, cross_p)]),
        "mark-mono.svg": svg(DOG_BOX, [("#000000", dog_p), ("#000000", cross_p)]),
        "icon.svg": None,  # filled below
    }

    # Launcher icon: 108x108 adaptive canvas, art inside the central 66dp safe circle.
    x0, y0, x1, y1 = DOG_BOX
    art = max(x1 - x0, y1 - y0)
    k = 62 / art                                   # 62dp wide: fits the safe zone with the ears
    ox, oy = x0 - (108 / k - (x1 - x0)) / 2, y0 - (108 / k - (y1 - y0)) / 2 + 2 / k
    icon_dog, icon_cross = trace(dog, ox, oy, k), crosshair_path(ox, oy, k)
    files["icon.svg"] = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 108 108"><rect width="108" height="108" fill="#FFFFFF"/>'
                         f'<path fill="{INK}" fill-rule="evenodd" d="{icon_dog}"/><path fill="{BLUE}" fill-rule="evenodd" d="{icon_cross}"/></svg>\n')
    for name, text in files.items():
        (OUT / name).write_text(text)

    def vector(name, wdp, hdp, vw, vh, parts):
        paths = "\n".join(f'    <path android:fillColor="{c}" android:fillType="evenOdd" android:pathData="{d}" />' for c, d in parts)
        (RES / "drawable" / name).write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n<!-- generated by brand/make_brand.py -->\n'
            f'<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            f'    android:width="{wdp}dp" android:height="{hdp}dp" android:viewportWidth="{vw:.2f}" android:viewportHeight="{vh:.2f}">\n'
            f"{paths}\n</vector>\n")

    vector("ic_launcher_foreground.xml", 108, 108, 108, 108, [("@color/brand_ink", icon_dog), ("@color/brand_blue", icon_cross)])
    vector("ic_launcher_monochrome.xml", 108, 108, 108, 108, [("#FFFFFFFF", icon_dog), ("#FFFFFFFF", icon_cross)])
    # notification icon: white silhouette on transparent, 24dp
    bx0, by0, bx1, by1 = DOG_BOX
    side = max(bx1 - bx0, by1 - by0)
    nk = 22 / side
    nox, noy = bx0 - (24 / nk - (bx1 - bx0)) / 2, by0 - (24 / nk - (by1 - by0)) / 2
    vector("ic_notification.xml", 24, 24, 24, 24, [("#FFFFFFFF", trace(dog, nox, noy, nk)), ("#FFFFFFFF", crosshair_path(nox, noy, nk))])
    # the mark for the app bar and the full logo for the welcome screen; colours follow light/dark theme
    mw, mh = bx1 - bx0, by1 - by0
    vector("brand_mark.xml", 40, round(40 * mh / mw), mw, mh,
           [("#FFFFFFFF", trace(under, bx0, by0)), ("@color/brand_ink", trace(dog, bx0, by0)),
            ("@color/brand_blue", crosshair_path(bx0, by0))])
    fx0, fy0, fx1, fy1 = FULL_BOX
    fw, fh = fx1 - fx0, fy1 - fy0
    vector("brand_logo.xml", 280, round(280 * fh / fw), fw, fh,
           [("#FFFFFFFF", trace(under, fx0, fy0)), ("@color/brand_ink", trace(dog, fx0, fy0)),
            ("@color/brand_blue", crosshair_path(fx0, fy0)),
            ("@color/brand_outline", trace(word_ink, fx0, fy0)), ("@color/brand_blue", trace(word_blue, fx0, fy0))])

    # dashboard: the mark inline, with its white face so it works on light and dark pages
    web = ROOT / "server/claimscout/web/mark.svg"
    web.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{bx0} {by0} {mw} {mh}" class="mark" aria-hidden="true">'
                   f'<path fill="#FFFFFF" d="{face_p}" fill-rule="evenodd"/><path fill="{INK}" fill-rule="evenodd" d="{dog_p}"/><path fill="{BLUE}" fill-rule="evenodd" d="{cross_p}"/></svg>\n')
    print("wrote", ", ".join(files), "+ android drawables + web/mark.svg")


if __name__ == "__main__":
    main()
