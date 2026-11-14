"""Rows of a household-examination spread (Tullberg blankett 37 style):
frame from the strong rules, 30 rows evenly spaced, year column from the
strong rule near mid-page to the next faint rule. Crops at full resolution.
python3 extract.py spread.jpg out/"""
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from grid import SCALE, adaptive, peaks, runs

NROWS = 30


def layout(img):
    w, h = img.size
    page = img.crop((0, 0, w // 2, h)).convert("L")
    small = page.resize((page.width // SCALE, page.height // SCALE))
    g = np.asarray(small); dark = adaptive(g)
    hp = runs(dark, 60, 1).sum(1); vp = runs(dark, 60, 0).sum(0)
    W, H = small.size
    frame = [r for r in peaks(hp, 0.25 * hp.max(), 8) if hp[r] > 0.6 * W]
    strong = peaks(vp, 0.25 * vp.max(), 8)
    # body: the last two full-width rules (header bottom, table bottom)
    top, bottom = frame[-2], frame[-1]
    # name column: strong rule in 10-25% of width; year: strong rule in 45-60%
    name_l = min((x for x in strong if 0.10 * W < x < 0.25 * W), key=lambda x: abs(x - 0.15 * W))
    year_l = min((x for x in strong if 0.45 * W < x < 0.60 * W), key=lambda x: abs(x - 0.51 * W))
    # faint rule to the right of the year: profile over the empty lower band
    band = g[int(top + 0.6 * (bottom - top)):bottom - 10].astype(float)
    loc = np.array([np.convolve(r, np.ones(41) / 41, mode="same") for r in band])
    prof = np.clip(loc - band, 0, None).mean(0)
    cand = [x for x in peaks(prof, 4 * np.median(prof), 6) if year_l + 40 < x < year_l + 120]
    year_r = cand[0] if cand else year_l + 72
    s = SCALE
    return page, dict(top=top * s, bottom=bottom * s, name_l=name_l * s, year_l=year_l * s, year_r=year_r * s)


def rows(page, L):
    rh = (L["bottom"] - L["top"]) / NROWS
    g = np.asarray(page)
    out = []
    for i in range(NROWS):
        y0 = int(L["top"] + i * rh - 0.12 * rh); y1 = int(L["top"] + (i + 1) * rh + 0.12 * rh)
        yc0 = int(L["top"] + i * rh + 0.15 * rh); yc1 = int(L["top"] + (i + 1) * rh - 0.1 * rh)
        name = (L["name_l"] + 8, y0, L["year_l"] - 4, y1)
        year = (L["year_l"] + 6, y0, L["year_r"] - 2, y1)
        # ink in the row core (between rules) of the name column
        core = g[yc0:yc1, L["name_l"] + 20:L["year_l"] - 20].astype(float)
        loc = core.mean()
        ink = float((core < loc - 40).mean())
        out.append(dict(row=i + 1, name=name, year=year, ink=ink))
    return out


def tess_digits(im, psm=7):
    p = subprocess.run(["tesseract", "stdin", "stdout", "--psm", str(psm), "-c",
                        "tessedit_char_whitelist=0123456789"], input=_png(im), capture_output=True)
    return p.stdout.decode().strip()


def _png(im):
    import io
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


if __name__ == "__main__":
    img = Image.open(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    page, L = layout(img)
    print(L)
    for r in rows(page, L):
        filled = r["ink"] > 0.004
        yc = page.crop(r["year"]); nc = page.crop(r["name"])
        t = tess_digits(yc.resize((yc.width // 2, yc.height // 2))) if filled else ""
        if filled:
            yc.save(out / f"y{r['row']:02d}.png"); nc.save(out / f"n{r['row']:02d}.png")
        print(f"{r['row']:2d} ink={r['ink']:.4f} {'*' if filled else ' '} tess={t!r}")
