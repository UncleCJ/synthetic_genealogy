"""
Dated map layers for the geography view: old maps and aerial photos from
data/input/maps, placed on the map so the view can draw them under its
events (a layer switcher and an opacity slider).

    python3 maplayers.py            # data/input/maps -> data/cache/maps (images + maps.json)
    python3 maplayers.py --list     # what each input file would become, without writing

Each layer is one image, cut to its map frame and axis-aligned in a Swedish
grid, plus the latitude and longitude of three of its corners; the view
places it with an affine transform (exact enough over a few kilometres).
No GDAL: the grids are converted with Lantmäteriet's Gauss-Krüger formulas.

Two kinds of input are recognised (anything else is listed and skipped):

- Lantmäteriet print-outs (PDF, "Skala 1:..., SWEREF 99 TM"): the frame's
  corner coordinates are in the text layer, and the map is the page's
  embedded raster, which fills the frame exactly (checked by aspect).
- Ekonomiska kartan scans from "Historiska kartor" (JPEG or TIFF named
  rak2_<hex>, the hex spelling an archive id RAK_J133-<sheet><yy>): the
  sheet name gives its 5 x 5 km square in RT 90 2.5 gon V, and the frame is
  found in the scan as the edges of the coloured map image. Unvalidated
  beyond the 1:10 000 sheets of south and central Sweden, and the 1950s
  sheets are drawn in RT 38, taken here as RT 90 (metres apart at most).

Labels and years come from the file name (a four-digit year), else the
sheet's edition (yy), else the PDF's creation year (a print-out of today's
map). Generalstaben and häradskartan scans need control points: not yet.
"""

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

GRS80 = (6378137.0, 1 / 298.257222101)
# Transverse Mercator parameters. RT 90 is given directly on GRS80
# (Lantmäteriet's "RT 90 2.5 gon V 0:-15" approximation, about a metre).
GRIDS = {
    "SWEREF 99 TM": dict(lon0=15.0, k0=0.9996, fn=0.0, fe=500000.0),
    "RT 90": dict(lon0=15 + 48 / 60 + 22.624306 / 3600, k0=1.00000561024, fn=-667.711, fe=1500064.274),
}
SCAN_WIDTH = 3000       # pixels across a warped ekonomiska kartan sheet (about 1.7 m each)


def grid_to_latlon(n, e, grid):
    """Northing, easting in a grid of GRIDS -> (lat, lon) in degrees.
    Lantmäteriet's inverse Gauss-Krüger series."""
    g = GRIDS[grid]
    a, f = GRS80
    e2 = f * (2 - f)
    m = f / (2 - f)
    ar = a / (1 + m) * (1 + m ** 2 / 4 + m ** 4 / 64)
    d = (m / 2 - 2 * m ** 2 / 3 + 37 * m ** 3 / 96 - m ** 4 / 360,
         m ** 2 / 48 + m ** 3 / 15 - 437 * m ** 4 / 1440,
         17 * m ** 3 / 480 - 37 * m ** 4 / 840,
         4397 * m ** 4 / 161280)
    A = e2 + e2 ** 2 + e2 ** 3 + e2 ** 4
    B = -(7 * e2 ** 2 + 17 * e2 ** 3 + 30 * e2 ** 4) / 6
    C = (224 * e2 ** 3 + 889 * e2 ** 4) / 120
    D = -(4279 * e2 ** 4) / 1260
    xi = (n - g["fn"]) / (g["k0"] * ar)
    eta = (e - g["fe"]) / (g["k0"] * ar)
    xp = xi - sum(d[i] * math.sin(2 * (i + 1) * xi) * math.cosh(2 * (i + 1) * eta) for i in range(4))
    ep = eta - sum(d[i] * math.cos(2 * (i + 1) * xi) * math.sinh(2 * (i + 1) * eta) for i in range(4))
    phi = math.asin(math.sin(xp) / math.cosh(ep))
    dlon = math.atan(math.sinh(ep) / math.cos(xp))
    s2 = math.sin(phi) ** 2
    lat = phi + math.sin(phi) * math.cos(phi) * (A + B * s2 + C * s2 ** 2 + D * s2 ** 3)
    return math.degrees(lat), g["lon0"] + math.degrees(dlon)


def corners(nmin, nmax, emin, emax, grid):
    """The three corners the view needs (north-west, north-east, south-west)."""
    r = lambda n, e: [round(v, 7) for v in grid_to_latlon(n, e, grid)]
    return {"nw": r(nmax, emin), "ne": r(nmax, emax), "sw": r(nmin, emin)}


# --- print-outs ---------------------------------------------------------

def printout_frame(text):
    """(grid, nmin, nmax, emin, emax) from a print-out's text layer, or None.
    The frame is labelled 'N 6400100' / 'E 401000' at its corners."""
    if "SWEREF 99 TM" not in text:
        return None
    ns = [int(v) for v in re.findall(r"\bN (\d{7})\b", text)]
    es = [int(v) for v in re.findall(r"\bE (\d{6})\b", text)]
    if len(set(ns)) != 2 or len(set(es)) != 2:
        return None
    return "SWEREF 99 TM", min(ns), max(ns), min(es), max(es)


def printout(pdf, out_jpg):
    """Extract the print-out's map raster to out_jpg; returns its frame."""
    from PIL import Image
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    frame = printout_frame(text)
    if not frame:
        raise ValueError("no SWEREF 99 TM frame in the text layer")
    _, nmin, nmax, emin, emax = frame
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdfimages", "-png", "-f", "1", "-l", "1", str(pdf), f"{tmp}/i"], check=True)
        imgs = [Image.open(p) for p in sorted(Path(tmp).glob("i-*.png"))]
        im = max((i for i in imgs if i.mode != "L"), key=lambda i: i.width * i.height)
        w, h = im.size
        if abs((w / h) / ((emax - emin) / (nmax - nmin)) - 1) > 0.01:
            raise ValueError(f"the page's raster ({w}x{h}) does not fill the frame; frame detection not done for print-outs")
        im.convert("RGB").save(out_jpg, quality=85)
    return frame


# --- ekonomiska kartan scans -------------------------------------------

def archive_id(name):
    """'..rak2_52414b5f4a3133332d31324633623630_1_1.jpg' -> 'RAK_J133-12F3b60'."""
    m = re.search(r"rak2_([0-9a-f]+)_", name)
    if not m:
        return None
    try:
        return bytes.fromhex(m.group(1)).decode("ascii")
    except ValueError:
        return None


def sheet_square(aid):
    """Ekonomiska kartan id -> (grid, nmin, nmax, emin, emax, yy), or None.
    'RAK_J133-12F3b60': 50 km square 12F (row 12 from 6100 km north, column
    F from 1200 km east), 5 km square 3b within it (row 3, column b),
    edition 60."""
    m = re.fullmatch(r"RAK_J133-(\d{1,2})([A-Z])(\d)([a-j])(\d{2})?", aid or "")
    if not m:
        return None
    row, col, sub, subcol, yy = m.groups()
    n0 = 6100000 + (int(row) - 1) * 50000 + int(sub) * 5000
    e0 = 1200000 + (ord(col) - ord("A")) * 50000 + (ord(subcol) - ord("a")) * 5000
    return "RT 90", n0, n0 + 5000, e0, e0 + 5000, yy


def _fit_edge(mask, side, near=0.03):
    """One straight edge of the coloured map image. The rough edge is where
    the share of coloured pixels per column (or row) first passes a third;
    within `near` of it, each row's first coloured pixel from that side;
    then a line through those, with outliers (pale patches at the edge)
    dropped. Returns (a, b): position = a + b * t, t the row (or column)."""
    import numpy as np
    m = mask if side in ("left", "right") else mask.T
    if side in ("right", "bottom"):
        m = m[:, ::-1]
    rows, width = m.shape
    prof = m[rows // 5:rows - rows // 5].mean(axis=0)
    rough = int(np.argmax(prof > 1 / 3))
    w = max(3, int(width * near))
    lo, hi = max(0, rough - w), min(width - 3, rough + w)
    hit = m[:, lo:hi] * m[:, lo + 1:hi + 1] * m[:, lo + 2:hi + 2]     # three coloured in a row
    t = np.arange(rows // 10, rows - rows // 10)
    t = t[hit[t].any(axis=1)]
    pos = lo + np.argmax(hit[t], axis=1).astype(float)
    a, b = float(np.median(pos)), 0.0
    for _ in range(5):
        keep = np.abs(pos - (a + b * t)) < 2.5
        b, a = np.polyfit(t[keep], pos[keep], 1)
    if side in ("right", "bottom"):
        a, b = width - 1 - a, -b
    return a, b


def frame_corners(rgb, sat=0.25):
    """Corners (top-left, bottom-left, bottom-right, top-right) of the
    coloured map image in a scanned sheet, as (x, y) pixels of `rgb` (an
    H x W x 3 array). Coloured: saturation above `sat`; the paper, text
    and the legend's small swatches cover too little of any column."""
    import numpy as np
    a = rgb.astype(float)
    mx, mn = a.max(axis=2), a.min(axis=2)
    mask = ((mx - mn) / np.maximum(mx, 1) > sat).astype(float)
    L, R = _fit_edge(mask, "left"), _fit_edge(mask, "right")      # x = a + b*y
    T, B = _fit_edge(mask, "top"), _fit_edge(mask, "bottom")      # y = a + b*x

    def meet(v, h):
        # x = v0 + v1*y and y = h0 + h1*x
        y = (h[0] + h[1] * v[0]) / (1 - h[1] * v[1])
        return v[0] + v[1] * y, y
    return [meet(L, T), meet(L, B), meet(R, B), meet(R, T)]


def scan(path, out_jpg, square):
    """Cut the sheet's map image out of the scan, squared to its 5 x 5 km."""
    import numpy as np
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(path).convert("RGB")
    k = max(1, im.width // 1500)
    small = np.asarray(im.reduce(k))
    cs = [(x * k, y * k) for x, y in frame_corners(small)]
    sides = [math.dist(cs[i], cs[(i + 1) % 4]) for i in range(4)]
    if max(sides) / min(sides) > 1.03:
        raise ValueError(f"the frame found is not square (sides {', '.join(f'{s:.0f}' for s in sides)} px)")
    quad = [v for c in cs for v in c]
    im.transform((SCAN_WIDTH, SCAN_WIDTH), Image.Transform.QUAD, quad, Image.Resampling.BICUBIC).save(out_jpg, quality=85)
    return square[:5]


# --- the folder ---------------------------------------------------------

def _year(name, fallback=None):
    m = re.search(r"\b(1[6-9]\d\d|20\d\d)\b", name)
    return int(m.group(1)) if m else fallback


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower().translate(str.maketrans("åäöé", "aaoe"))).strip("-")


def plan(folder):
    """One entry per input file: (path, kind, label, year) or a skip reason."""
    out = []
    files = sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))
    sheets = {}
    for p in files:
        aid = archive_id(p.name)
        if aid is not None and p.suffix.lower() in (".jpg", ".jpeg", ".tif", ".tiff"):
            sq = sheet_square(aid)
            if not sq:
                out.append((p, None, f"{aid}: not an ekonomiska kartan sheet (needs control points)", None))
                continue
            # one file per sheet: the TIFF when both are there
            if aid not in sheets or p.suffix.lower() in (".tif", ".tiff"):
                sheets[aid] = p
        elif p.suffix.lower() == ".pdf" and aid is None:
            date = subprocess.run(["pdfinfo", str(p)], capture_output=True, text=True).stdout
            created = re.search(r"CreationDate:.*?(\d{4})\s*\S*$", date, re.M)
            year = _year(p.stem, int(created.group(1)) if created else None)
            label = re.sub(r"\s*\d{4}\s*|-\d+$", " ", p.stem).strip()
            out.append((p, "printout", label, year))
        else:
            out.append((p, None, "not a print-out or ekonomiska kartan scan", None))
    for aid, p in sheets.items():
        sq = sheet_square(aid)
        year = _year(p.stem, 1900 + int(sq[5]) if sq[5] else None)
        out.append((p, "scan", f"Ekonomiska kartan {aid.split('-')[1][:-2] if sq[5] else aid.split('-')[1]}", year))
    return out


def build(folder, dest):
    dest.mkdir(parents=True, exist_ok=True)
    layers = []
    for p, kind, label, year in plan(folder):
        if kind is None:
            continue
        lid = _slug(f"{label} {year or ''}")
        img = f"{lid}.jpg"
        try:
            if kind == "printout":
                grid, nmin, nmax, emin, emax = printout(p, dest / img)
            else:
                grid, nmin, nmax, emin, emax = scan(p, dest / img, sheet_square(archive_id(p.name)))
        except (ValueError, subprocess.CalledProcessError) as e:
            print(f"  skipped {p.name}: {e}", file=sys.stderr)
            continue
        layers.append({"id": lid, "label": label, "year": year, "img": img, "src": p.name,
                       "grid": grid, "frame": [nmin, nmax, emin, emax], **corners(nmin, nmax, emin, emax, grid)})
        print(f"  {label} ({year}): {p.name} -> {img}")
    layers.sort(key=lambda d: (d["year"] or 9999, d["label"]))
    (dest / "maps.json").write_text(json.dumps(layers, ensure_ascii=False, indent=1), encoding="utf-8")
    return layers


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    ap.add_argument("--list", action="store_true", help="show what each input file would become; write nothing")
    a = ap.parse_args(argv)
    import config
    data = config.load()["data_dir"]
    folder, dest = data.layer("input") / "maps", data.layer("cache") / "maps"
    if not folder.is_dir():
        sys.exit(f"no {folder}: put the downloaded maps there")
    if a.list:
        for p, kind, label, year in plan(folder):
            print(f"{p.name}: {kind or 'skip'} {label}{f' ({year})' if year else ''}")
        return
    layers = build(folder, dest)
    print(f"maplayers: {len(layers)} layers -> {dest / 'maps.json'}")


if __name__ == "__main__":
    main()
