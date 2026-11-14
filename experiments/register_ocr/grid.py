"""Ruled-line grid of a pre-printed register page, numpy only.
python3 grid.py page.jpg left|right out_prefix"""
import sys
import numpy as np
from PIL import Image, ImageDraw

SCALE = 2  # work at half resolution


def otsu(g):
    hist = np.bincount(g.ravel(), minlength=256).astype(float)
    p = hist / hist.sum()
    w = np.cumsum(p); mu = np.cumsum(p * np.arange(256)); mt = mu[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        s = (mt * w - mu) ** 2 / (w * (1 - w))
    return int(np.nanargmax(s))


def adaptive(g, win=31, off=12):
    """Dark where the pixel is off below its local mean (integral image box filter)."""
    f = g.astype(np.float64)
    ii = np.pad(np.cumsum(np.cumsum(f, 0), 1), ((1, 0), (1, 0)))
    r = win // 2; H, W = g.shape
    y0 = np.clip(np.arange(H) - r, 0, H); y1 = np.clip(np.arange(H) + r + 1, 0, H)
    x0 = np.clip(np.arange(W) - r, 0, W); x1 = np.clip(np.arange(W) + r + 1, 0, W)
    s = ii[y1][:, x1] - ii[y0][:, x1] - ii[y1][:, x0] + ii[y0][:, x0]
    n = (y1 - y0)[:, None] * (x1 - x0)[None, :]
    return f < s / n - off


def runs(mask, L, axis):
    """True where a run of >= L dark pixels along axis covers the pixel (approx: window sum)."""
    c = np.cumsum(mask, axis=axis, dtype=np.int32)
    pad = [(0, 0), (0, 0)]; pad[axis] = (1, 0)
    c = np.pad(c, pad)
    if axis == 1:
        s = c[:, L:] - c[:, :-L]
        out = np.zeros_like(mask); out[:, L // 2:L // 2 + s.shape[1]] = s >= L * 0.9
    else:
        s = c[L:, :] - c[:-L, :]
        out = np.zeros_like(mask); out[L // 2:L // 2 + s.shape[0], :] = s >= L * 0.9
    return out


def peaks(profile, min_val, min_gap):
    idx = [i for i in range(1, len(profile) - 1)
           if profile[i] >= min_val and profile[i] >= profile[i - 1] and profile[i] >= profile[i + 1]]
    out = []
    for i in idx:
        if out and i - out[-1] < min_gap:
            if profile[i] > profile[out[-1]]:
                out[-1] = i
        else:
            out.append(i)
    return out


def grid(img, side):
    w, h = img.size
    page = img.crop((0, 0, w // 2, h) if side == "left" else (w // 2, 0, w, h))
    page = page.convert("L").resize((page.width // SCALE, page.height // SCALE))
    g = np.asarray(page)
    dark = adaptive(g)
    H = runs(dark, 60, 1)
    V = runs(dark, 60, 0)
    hp, vp = H.sum(1), V.sum(0)
    rows = peaks(hp, 0.25 * hp.max(), 8)
    cols = peaks(vp, 0.25 * vp.max(), 8)
    return page, g, dark, rows, cols


if __name__ == "__main__":
    img = Image.open(sys.argv[1]); side = sys.argv[2]; out = sys.argv[3]
    page, g, dark, rows, cols = grid(img, side)
    print("size", page.size, "rows", len(rows), rows)
    print("cols", len(cols), cols)
    vis = page.convert("RGB"); d = ImageDraw.Draw(vis)
    for y in rows: d.line([(0, y), (page.width, y)], fill=(255, 0, 0), width=2)
    for x in cols: d.line([(x, 0), (x, page.height)], fill=(0, 0, 255), width=2)
    vis.resize((page.width // 2, page.height // 2)).save(out + "_grid.png")
