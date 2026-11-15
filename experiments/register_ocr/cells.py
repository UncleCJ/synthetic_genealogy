"""cells.py IMG OUT: name-column text lines and the age cell on the left
page, read with Riksarkivet's TrOCR (see README). Sketch, unvalidated.

Columns from grid.py's rules (the widest gap is the name column, the next
one the age); rules removed, text lines from the ink profile, tall bands
split at ink valleys into single handwritten lines. Output per line: box,
name text, age text (tab-separated)."""
import sys, numpy as np, torch
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from grid import grid, adaptive, runs, SCALE
from PIL import Image
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
img = Image.open(sys.argv[1]).convert("RGB"); W, H = img.size
page, g, dark, rows, cols = grid(img, "left"); pw, ph = page.size
# name column: widest gap between vertical rules, if it is plausible
name = age = None
if len(cols) >= 3:
    gaps = sorted(((cols[i+1]-cols[i], i) for i in range(len(cols)-1)), reverse=True)
    w, i = gaps[0]
    if 0.25*pw < w < 0.7*pw and cols[i] > 0.2*pw:
        name = (cols[i], cols[i+1])
        right = [c for c in cols if c > cols[i+1]]
        age = (cols[i+1], right[min(1, len(right)-1)] if right else cols[i+1] + 0.12*pw)
if not name:
    name, age = (0.27*pw, 0.70*pw), (0.70*pw, 0.80*pw)
x0, x1 = int(name[0]) + 3, int(name[1]) - 3
band = dark[:, x0:x1].copy()
band &= ~runs(band, 40, 1)                       # drop horizontal rules
prof = band.sum(1); thr = max(3, 0.04 * (x1 - x0))
lines, y = [], None
for r, v in enumerate(prof):
    if v > thr and y is None: y = r
    if v <= thr and y is not None:
        if r - y >= 6: lines.append((y, r))
        y = None
# merge very close fragments, pad
merged = []
for a, b in lines:
    if merged and a - merged[-1][1] < 3: merged[-1] = (merged[-1][0], b)
    else: merged.append((a, b))
# split tall bands at ink valleys into single handwritten lines
Lh = max(14, 0.022 * ph)
sm = np.convolve(prof, np.ones(5) / 5, mode="same")
split = []
for a, b in merged:
    if b - a < 1.6 * Lh:
        split.append((a, b)); continue
    seg = sm[a:b]; cuts = [a]
    k = int(0.6 * Lh)
    while k < len(seg) - int(0.6 * Lh):
        w = seg[k:k + int(0.8 * Lh)]
        j = k + int(np.argmin(w))
        if seg[j] < 0.35 * seg.max() and j - (cuts[-1] - a) > 0.6 * Lh and len(seg) - j > 0.6 * Lh:
            cuts.append(a + j); k = j + int(0.6 * Lh)
        else:
            k += int(0.4 * Lh)
    cuts.append(b)
    split += [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]
lines = [(a, b) for a, b in split if 6 <= b - a < 2.2 * Lh]
M = "Riksarkivet/trocr-base-handwritten-hist-swe-2"
dev = "mps" if torch.backends.mps.is_available() else "cpu"
proc = TrOCRProcessor.from_pretrained(M); model = VisionEncoderDecoderModel.from_pretrained(M).to(dev).eval()
def crop(xa, xb, a, b):
    p = 4
    return img.crop((int(xa*SCALE), int((a-p)*SCALE), int(xb*SCALE), int((b+p)*SCALE)))
crops = []
for a, b in lines:
    crops += [crop(x0, x1, a, b), crop(age[0], age[1], a, b)]
texts = []
for i in range(0, len(crops), 8):
    px = proc(images=crops[i:i+8], return_tensors="pt").pixel_values.to(dev)
    with torch.no_grad(): ids = model.generate(px, max_new_tokens=48, num_beams=3)
    texts += proc.batch_decode(ids, skip_special_tokens=True)
with open(sys.argv[2], "w") as out:
    for k, (a, b) in enumerate(lines):
        out.write("%.3f %.3f %.3f %.3f\t%s|1\t%s\n" % (x0/pw/2, a/ph, (x1-x0)/pw/2, (b-a)/ph, texts[2*k], texts[2*k+1]))
print(sys.argv[1].split("/")[-1], "cols", len(cols), "name", [int(v) for v in name], "lines", len(lines))
