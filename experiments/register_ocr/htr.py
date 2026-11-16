"""Re-read the shelf's Vision line boxes with Riksarkivet's TrOCR (sketch).

HF_HUB_OFFLINE=1 ~/.cache/sg-htr-venv/bin/python htr.py ROOT [--follow]

For each <volume>/ocr/<image>.vision.tsv without a .trocr.tsv beside it,
skipping covers (images 1, 2 and the last) and unpaginated pages that
shelf.py frontmatter did not class as index, crop each line box and read it
with Riksarkivet/trocr-base-handwritten-hist-swe-2 (needs transformers<5).
Output has the same format as the Vision file, confidence 1. Pages Vision reads
with high confidence (typed or printed: 80% of five or more lines at 0.5
or above) are left to Vision; the model is for handwriting. Raw and
untuned: Vision's boxes split or merge handwritten lines. About 50 s a
page on MPS. --follow polls every ten minutes, stops after an idle day."""
import os
import re
import sys
import time
from pathlib import Path

import torch
from PIL import Image
from transformers import TrOCRProcessor, VisionEncoderDecoderModel

M = "Riksarkivet/trocr-base-handwritten-hist-swe-2"


def boxes(im, tsv):
    W, H = im.size
    p = 0.006
    for line in open(tsv, encoding="utf-8"):
        b = line.split("\t", 1)[0]
        x, y, w, h = map(float, b.split())
        if h > 0.08 or w < 0.015:
            continue
        yield (x, y, w, h), im.crop((int((x - p) * W), int((y - p) * H),
                                     int((x + w + p) * W), int((y + h + p) * H)))


def typed(tsv):
    c = [float(l.rstrip("\n").split("\t")[1].split("  ")[0].rsplit("|", 1)[1])
         for l in open(tsv, encoding="utf-8")]
    return len(c) >= 5 and sum(x >= 0.5 for x in c) >= 0.8 * len(c)


def todo(root):
    fm = {}
    if (root / "frontmatter.tsv").exists():
        for l in open(root / "frontmatter.tsv", encoding="utf-8").read().splitlines()[1:]:
            f = l.split("\t")
            fm[(f[0], int(f[2]))] = f[5]
    for tsv in sorted(root.glob("*/*/ocr/*.vision.tsv")):
        out = tsv.with_name(tsv.name.replace(".vision.", ".trocr."))
        if out.exists():
            continue
        vol = tsv.parent.parent
        n = int(re.match(r"Bild (\d+)", tsv.name).group(1))
        m = re.search(r"^- Bilder: (\d+)", (vol / "volume.md").read_text(encoding="utf-8"), re.M)
        if n in (1, 2) or (m and n == int(m.group(1))):
            continue
        if fm.get((vol.name.rsplit(" ", 1)[-1], n), "index") != "index":
            continue
        if "Sida" not in tsv.name and (vol.name.rsplit(" ", 1)[-1], n) not in fm:
            continue   # unpaginated, not yet classed: wait for frontmatter
        if typed(tsv):
            continue
        img = vol / tsv.name.replace(".vision.tsv", ".jpg")
        if img.exists():
            yield img, tsv, out


def main(root, follow):
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    proc = TrOCRProcessor.from_pretrained(M)
    model = VisionEncoderDecoderModel.from_pretrained(M).to(dev).eval()
    idle = 0
    while True:
        done = 0
        for img, tsv, out in todo(root):
            im = Image.open(img).convert("RGB")
            bx = list(boxes(im, tsv))
            lines = []
            for i in range(0, len(bx), 8):
                chunk = bx[i:i + 8]
                px = proc(images=[c for _, c in chunk], return_tensors="pt").pixel_values.to(dev)
                with torch.no_grad():
                    ids = model.generate(px, max_new_tokens=64, num_beams=3)
                for (b, _), t in zip(chunk, proc.batch_decode(ids, skip_special_tokens=True)):
                    lines.append("%.3f %.3f %.3f %.3f\t%s|1\n" % (*b, t))
            tmp = out.with_name(out.name + ".%d.part" % os.getpid())
            tmp.write_text("".join(lines), encoding="utf-8")
            tmp.rename(out)
            done += 1
            print(time.strftime("%F %T"), "trocr", img.relative_to(root), len(lines), flush=True)
        if not follow:
            return
        idle = 0 if done else idle + 1
        if idle >= 144:
            return
        time.sleep(600)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), "--follow" in sys.argv)
