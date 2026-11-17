"""Read a ruled register page cell by cell with Riksarkivet's TrOCR (sketch,
unvalidated; see README).

python3 cells.py IMG OUT [--vision TSV] [--cols name,in,out]

Columns: printed headers in the page's Vision lines (--vision; the shelf
keeps them as ocr/<image>.vision.tsv) name them (name, in, out, born,
died, age), the form's vertical rules (grid.py) give their edges; a header
with no rule near it gets a fixed width. Without headers, the old rule
heuristic on the left page: the widest gap is the name column, the next
the age. Rows: text lines from the ink profile of the name column, tall
bands split at ink valleys. Each row's cells are read with TrOCR.
Output: one row per line, box of the name cell (page fractions), then
`column=text` per column, tab-separated."""
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from grid import SCALE, adaptive, peaks, runs  # noqa: E402

# printed headers, loosely (Vision misreads print too: "Jutlytad")
HEADERS = {
    "in": r"(hit|in|ink)fl[iy]?[tl]+ad|^inflytt",
    "out": r"(bort|ut|jut)fl[iy]?[tl]+ad|utfl[iy]?t",
    "name": r"\bnamn\b|personernas",
    "born": r"födelse|\bfödd?e?\b",
    "died": r"^död\b|dödsår|^död\.",
    "age": r"^ålder",
}


def header_columns(vision_tsv, top=0.25):
    """{column: x centre} from printed headers in the top of the page."""
    found = {}
    for line in open(vision_tsv, encoding="utf-8"):
        box, _, text = line.rstrip("\n").partition("\t")
        x, y, w, h = map(float, box.split())
        t = text.split("  ")[0].rsplit("|", 1)[0].strip()
        if y > top:
            continue
        for k, rx in HEADERS.items():
            if k not in found and re.search(rx, t, re.I):
                found[k] = (x + w / 2, y + h)
    return found


def volume_heads(vol_dir):
    """{column: (x, y)}: the median header position over a volume's pages,
    for pages where a header is missing or misread."""
    from statistics import median
    seen = {}
    for tsv in Path(vol_dir).glob("ocr/*.vision.tsv"):
        for k, xy in header_columns(tsv).items():
            seen.setdefault(k, []).append(xy)
    return {k: (median(x for x, _ in v), median(y for _, y in v))
            for k, v in seen.items() if len(v) >= 3}


def rules(dark):
    """x of vertical rules (page fractions) across the whole image."""
    V = runs(dark, 60, 0)
    vp = V.sum(0)
    return [c / dark.shape[1] for c in peaks(vp, 0.25 * vp.max(), 8)]


def column_edges(cx, xs, width=0.06):
    left = [x for x in xs if x < cx - 0.005]
    right = [x for x in xs if x > cx + 0.005]
    a = left[-1] if left and cx - left[-1] < 0.2 else cx - width / 2
    b = right[0] if right and right[0] - cx < 0.2 else cx + width / 2
    return a, b


def text_lines(dark, x0, x1, y0, ph):
    """(top, bottom) pixel rows of handwritten lines in a column band."""
    band = dark[:, x0:x1].copy()
    band &= ~runs(band, 40, 1)                       # drop horizontal rules
    band[:y0] = False
    prof = band.sum(1)
    thr = max(3, 0.04 * (x1 - x0))
    lines, y = [], None
    for r, v in enumerate(prof):
        if v > thr and y is None:
            y = r
        if v <= thr and y is not None:
            if r - y >= 6:
                lines.append((y, r))
            y = None
    merged = []
    for a, b in lines:
        if merged and a - merged[-1][1] < 3:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    Lh = max(14, 0.022 * ph)
    sm = np.convolve(prof, np.ones(5) / 5, mode="same")
    split = []
    for a, b in merged:
        if b - a < 1.6 * Lh:
            split.append((a, b))
            continue
        seg, cuts, k = sm[a:b], [a], int(0.6 * Lh)
        while k < len(seg) - int(0.6 * Lh):
            w = seg[k:k + int(0.8 * Lh)]
            j = k + int(np.argmin(w))
            if seg[j] < 0.35 * seg.max() and j - (cuts[-1] - a) > 0.6 * Lh and len(seg) - j > 0.6 * Lh:
                cuts.append(a + j)
                k = j + int(0.6 * Lh)
            else:
                k += int(0.4 * Lh)
        cuts.append(b)
        split += [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]
    return [(a, b) for a, b in split if 6 <= b - a < 2.2 * Lh]


def layout(img, vision=None, want=("name", "in", "out"), vol=None):
    """({column: (x0, x1) as fractions}, dark mask, first text row). vol:
    volume_heads(), filling headers this page lacks."""
    g = np.asarray(img.convert("L").resize((img.width // SCALE, img.height // SCALE)))
    dark = adaptive(g)
    xs = rules(dark)
    heads = header_columns(vision) if vision else {}
    for k, xy in (vol or {}).items():
        if k not in heads or abs(heads[k][0] - xy[0]) > 0.05:
            heads[k] = xy
    cols = {k: column_edges(heads[k][0], xs) for k in want if k in heads}
    if "name" not in cols and "born" in heads:
        # församlingsbok: no printed name header; the name stands left of the birth column
        b0 = column_edges(heads["born"][0], xs)[0]
        cols["name"] = (max(0.02, b0 - 0.2), b0)
    elif "name" not in cols and "in" in heads:
        # neither: on the forms seen, the name column ends about 0.19 left of "moved in"
        cols["name"] = (max(0.02, heads["in"][0] - 0.38), heads["in"][0] - 0.19)
    y0 = max((y for _, y in heads.values()), default=0.12) + 0.01
    if "name" not in cols:            # the old heuristic, left page
        left = [x for x in xs if x < 0.5]
        gaps = sorted(((left[i + 1] - left[i], i) for i in range(len(left) - 1)), reverse=True)
        if gaps and 0.12 < gaps[0][0] < 0.35 and left[gaps[0][1]] > 0.1:
            i = gaps[0][1]
            cols["name"] = (left[i], left[i + 1])
            rest = [x for x in left if x > left[i + 1]]
            if "age" in want or not heads:
                cols.setdefault("age", (left[i + 1], rest[min(1, len(rest) - 1)] if rest else left[i + 1] + 0.06))
        else:
            cols["name"] = (0.135, 0.35)
    return cols, dark, y0


_MODEL = []   # processor, model, device: loaded once per process


def read(img_path, vision=None, want=("name", "in", "out"), vol=None):
    import torch
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    img = Image.open(img_path).convert("RGB")
    cols, dark, y0 = layout(img, vision, want, vol)
    H, W = dark.shape
    nx0, nx1 = (int(v * W) for v in cols["name"])
    rows = text_lines(dark, nx0 + 3, nx1 - 3, int(y0 * H), H)
    if not _MODEL:
        M = "Riksarkivet/trocr-base-handwritten-hist-swe-2"
        dev = "mps" if torch.backends.mps.is_available() else "cpu"
        _MODEL.extend([TrOCRProcessor.from_pretrained(M),
                       VisionEncoderDecoderModel.from_pretrained(M).to(dev).eval(), dev])
    proc, model, dev = _MODEL
    names = list(cols)
    crops = []
    for a, b in rows:
        for k in names:
            x0, x1 = cols[k]
            crops.append(img.crop((int(x0 * img.width), int((a - 4) * SCALE),
                                   int(x1 * img.width), int((b + 4) * SCALE))))
    texts = []
    for i in range(0, len(crops), 8):
        px = proc(images=crops[i:i + 8], return_tensors="pt").pixel_values.to(dev)
        with torch.no_grad():
            ids = model.generate(px, max_new_tokens=48, num_beams=3)
        texts += proc.batch_decode(ids, skip_special_tokens=True)
    out = []
    for r, (a, b) in enumerate(rows):
        cells = dict(zip(names, texts[r * len(names):(r + 1) * len(names)]))
        out.append(((cols["name"][0], a / H, cols["name"][1] - cols["name"][0], (b - a) / H), cells))
    return cols, out


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2:
        raise SystemExit(__doc__)
    vis = a[a.index("--vision") + 1] if "--vision" in a else None
    want = tuple(a[a.index("--cols") + 1].split(",")) if "--cols" in a else ("name", "in", "out", "age")
    cols, rows = read(a[0], vis, want)
    with open(a[1], "w", encoding="utf-8") as o:
        for (x, y, w, h), cells in rows:
            o.write("%.3f %.3f %.3f %.3f\t%s\n" % (x, y, w, h, "\t".join(f"{k}={v}" for k, v in cells.items())))
    print(Path(a[0]).name, {k: tuple(round(v, 3) for v in c) for k, c in cols.items()}, "rows", len(rows))
