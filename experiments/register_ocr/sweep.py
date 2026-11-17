"""Find a place's pages in whole volumes by reading only the page heads (sketch, unvalidated).

PY=~/.cache/sg-htr-venv/bin/python; export HF_HUB_OFFLINE=1
$PY sweep.py locate TAG ID... --names "Name,..." [--frac 0.5] [--tries 12]
$PY sweep.py heads TAG ID... --names "Name,Variant,..." [--step 3] [--floor-gb 5]
$PY sweep.py pages TAG [--pad 1] [--width 2600] [--floor-gb 5]
python3 sweep.py report TAG

For household examinations and parish books whose pages are headed by
rote, village or property. `heads` takes every STEP-th numbered image of
each volume (Riksarkivet image-series ids), fetches only the left page's
top quarter (a small IIIF region, into <volume>/heads/), finds its lines
with Apple Vision and reads them with Riksarkivet's TrOCR, and keeps
every image whose head text fuzzily matches a name, in ROOT/sweep/TAG.tsv
(all head text in TAG-heads.tsv, to look for the rote by hand). `pages`
fetches the matched images and their neighbours (gaps up to two steps
filled) at WIDTH px into the volume folder as the shelf does, and reads
them whole (Vision lines, TrOCR text: ocr/*.vision.tsv, *.trocr.tsv).
`report` prints the TrOCR text per volume and page, lines in reading
order, for a person (or Claude) to read: raw, with the model's errors.
Images extra to the matches can be listed in ROOT/sweep/TAG-extra.tsv
(id, image). Layout, cookie and pacing as shelf.py; ROOT is data/archive.
TrOCR runs about 3 s per head and 50 s per page on Apple MPS."""
import difflib
import gzip
import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import shelf  # noqa: E402
from shelf import MAIN, Vol, get_image, http, log, write_volume_md, free_gb  # noqa: E402


def opt(args, k, d):
    return args[args.index(k) + 1] if k in args else d


def norm(s):
    s = unicodedata.normalize("NFC", s.lower())
    for a, b in (("w", "v"), ("ph", "f"), ("ſ", "s"), ("é", "e"), ("aa", "å")):
        s = s.replace(a, b)
    return re.sub(r"[^a-zåäö ]", " ", s)


def score(text, names):
    """Best fuzzy ratio of any name against any run of 1-2 words."""
    w = norm(text).split()
    grams = w + [a + b for a, b in zip(w, w[1:])] + [a + " " + b for a, b in zip(w, w[1:])]
    best = (0.0, "")
    for n in names:
        nn = norm(n).replace(" ", "")
        for g in grams:
            g2 = g.replace(" ", "")
            if len(g2) < max(3, len(nn) - 3):
                continue
            r = difflib.SequenceMatcher(None, nn, g2[:len(nn) + 2]).ratio()
            if r > best[0]:
                best = (r, n)
    return best


class Reader:
    """Vision for line boxes, TrOCR for the text (loaded once)."""
    def __init__(s, root):
        s.exe = root / ".bin/vision"
        if not s.exe.exists():
            s.exe.parent.mkdir(exist_ok=True)
            subprocess.run(["swiftc", "-O", str(Path(__file__).with_name("vision.swift")),
                            "-o", str(s.exe)], check=True)
        import torch
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        import htr
        s.torch, s.htr = torch, htr
        s.dev = "mps" if torch.backends.mps.is_available() else "cpu"
        s.proc = TrOCRProcessor.from_pretrained(htr.M)
        s.model = VisionEncoderDecoderModel.from_pretrained(htr.M).to(s.dev).eval()

    def vision(s, img, out):
        if not out.exists():
            r = subprocess.run([str(s.exe), str(img)], capture_output=True, text=True)
            out.parent.mkdir(exist_ok=True)
            out.write_text(r.stdout, encoding="utf-8")
        return out

    def trocr(s, img, vtsv, out):
        """TrOCR for the lines Vision is unsure of (handwriting); Vision's
        own text kept for the confident ones (print)."""
        if out.exists():
            return out.read_text(encoding="utf-8")
        from PIL import Image
        im = Image.open(img).convert("RGB")
        W, H = im.size
        p = 0.006
        bx, lines = [], []
        for line in open(vtsv, encoding="utf-8"):
            b, c = line.rstrip("\n").split("\t", 1)
            x, y, w, h = map(float, b.split())
            if h > 0.08 or w < 0.015:
                continue
            t, conf = c.split("  ")[0].rsplit("|", 1)
            if float(conf) >= 0.5:
                lines.append("%.3f %.3f %.3f %.3f\t%s|%s\n" % (x, y, w, h, t, conf))
                continue
            bx.append(((x, y, w, h), im.crop((int((x - p) * W), int((y - p) * H),
                                              int((x + w + p) * W), int((y + h + p) * H)))))
        for i in range(0, len(bx), 8):
            chunk = bx[i:i + 8]
            px = s.proc(images=[c for _, c in chunk], return_tensors="pt").pixel_values.to(s.dev)
            with s.torch.no_grad():
                ids = s.model.generate(px, max_new_tokens=64, num_beams=3)
            for (b, _), t in zip(chunk, s.proc.batch_decode(ids, skip_special_tokens=True)):
                lines.append("%.3f %.3f %.3f %.3f\t%s|1\n" % (*b, t))
        out.write_text("".join(lines), encoding="utf-8")
        return out.read_text(encoding="utf-8")


def volume(root, vid):
    v = Vol(root, vid, {})
    if v.load():
        return v
    code, body = http(f"https://lbiiif.riksarkivet.se/arkis!{vid}/manifest")
    if code != 200:
        log(root, "manifest", vid, code, body[:80])
        return None
    v.m = json.loads(body)
    v.place()
    (v.dir / "manifest.json.gz").write_bytes(gzip.compress(body))
    write_volume_md(v, {})
    time.sleep(1.0)
    return v


def paged(v):
    return [i for i, c in enumerate(v.canvases(), 1) if "Sida" in shelf.sv(c["label"])]


def head_image(v, n, floor):
    out = v.dir / "heads" / (v.label(n) + ".jpg")
    if out.exists():
        return out
    if free_gb(v.root) < floor:
        raise SystemExit(f"disk floor {floor} GB reached")
    c = v.canvases()[n - 1]
    W, H = int(c["width"]), int(c["height"])
    url = (f"https://lbiiif.riksarkivet.se/v2/arkis!{v.id}_{n:05d}/"
           f"0,0,{W // 2},{H // 4}/1200,/0/default.jpg")
    code, body = http(url)
    time.sleep(0.6)
    if code == 200 and body[:2] == b"\xff\xd8":
        out.parent.mkdir(exist_ok=True)
        out.write_bytes(body)
        return out
    log(v.root, "head", v.id, n, code, body[:80])
    return None


def text_of(tsv_text):
    rows = []
    for line in tsv_text.splitlines():
        b, c = line.split("\t", 1)
        x, y, w, h = map(float, b.split())
        rows.append((round(y / 0.012), x, c.split("  ")[0].rsplit("|", 1)[0]))
    return [t for _, _, t in sorted(rows)]


def heads(root, tag, ids, names, step, floor):
    rd = Reader(root)
    sd = root / "sweep"
    sd.mkdir(exist_ok=True)
    hits = sd / f"{tag}.tsv"
    allh = sd / f"{tag}-heads.tsv"
    seen = set()
    if allh.exists():
        seen = {tuple(l.split("\t")[:2]) for l in allh.read_text(encoding="utf-8").splitlines()}
    for vid in ids:
        v = volume(root, vid)
        if not v:
            continue
        pg = paged(v)
        for n in pg[::step]:
            if (vid, str(n)) in seen:
                continue
            img = head_image(v, n, floor)
            if not img:
                continue
            vt = rd.vision(img, img.parent / "ocr" / (img.stem + ".vision.tsv"))
            txt = " / ".join(text_of(rd.trocr(img, vt, img.parent / "ocr" / (img.stem + ".trocr.tsv"))))
            with open(allh, "a", encoding="utf-8") as o:
                o.write(f"{vid}\t{n}\t{v.label(n)}\t{txt}\n")
            r, name = score(txt, names)
            if r >= 0.8:
                with open(hits, "a", encoding="utf-8") as o:
                    o.write(f"{vid}\t{n}\t{v.label(n)}\t{name}\t{r:.2f}\t{txt}\n")
            print(time.strftime("%T"), vid, n, f"{r:.2f}", name if r >= 0.8 else "", txt[:70], flush=True)


MIN_REG = 0.7  # a register line is short; one misread letter in a seven-letter name scores about 0.71
CARD = re.compile(r"BEGIN|BÖRJAN|LANDSARKIV|RIKSARKIV|GENEALOGICAL|CHURCH RECORDS|SLUT\b", re.I)


def register(root, tag, ids, names, width, floor):
    """Read the unnumbered front images (farm/property registers) whole;
    for each line naming a place, take the numbers on it as page (Sida)
    numbers and list those images in TAG-extra.tsv."""
    rd = Reader(root)
    sd = root / "sweep"
    sd.mkdir(exist_ok=True)
    def folios(v):
        out = {}
        for i, c in enumerate(v.canvases(), 1):
            m = re.search(r"Sida\s+(\d+)", shelf.sv(c["label"]))
            if m:
                out.setdefault(int(m.group(1)), (v.id, i))
        return out
    vols = [volume(root, vid) for vid in ids]
    for j, v in enumerate(vols):
        if not v:
            continue
        sida = folios(v)
        if j + 1 < len(vols) and vols[j + 1]:   # Del I's register covers Del II too
            for k, hit in folios(vols[j + 1]).items():
                sida.setdefault(k, hit)
        vid = v.id
        front, _ = v.unpaginated()
        for n in front:
            r = get_image(v, n, floor, size=f"{width},")
            img = v.dir / (v.label(n) + ".jpg")
            if r == "full":
                raise SystemExit(f"disk floor {floor} GB reached")
            if not img.exists():
                continue
            vt = rd.vision(img, v.dir / "ocr" / (img.stem + ".vision.tsv"))
            if CARD.search(vt.read_text(encoding="utf-8")):
                continue
            txt = rd.trocr(img, vt, v.dir / "ocr" / (img.stem + ".trocr.tsv"))
            bx = []
            for line in txt.splitlines():
                b, c = line.split("\t", 1)
                bx.append((*map(float, b.split()), c.rsplit("|", 1)[0]))
            for x, y, w, h, t in bx:
                if len(t.split()) > 4:   # a register entry is a name and a folio or two
                    continue
                sc, name = score(t, names)
                if sc < MIN_REG:
                    continue
                nums = [int(k) for k in re.findall(r"\b(\d{1,3})\b", t)]
                if not nums:   # folios are boxes of their own, right of the name, within its height
                    right = [t2 for x2, y2, w2, h2, t2 in bx
                             if y - 0.004 < y2 + h2 / 2 < y + h + 0.004
                             and x + w - 0.01 < x2 < x + w + 0.3 and re.fullmatch(r"[\d\s.,-]+", t2)]
                    nums = [int(k) for t2 in right for k in re.findall(r"\d{1,3}", t2)]
                for k in nums:
                    if k in sida:
                        tv, ti = sida[k]
                        with open(sd / f"{tag}-extra.tsv", "a", encoding="utf-8") as o:
                            o.write(f"{tv}\t{ti}\tregister {vid} bild {n}: {name} {sc:.2f}: {t} -> sida {k}\n")
                print(vid, n, name, f"{sc:.2f}", t, nums, [sida.get(k) for k in nums], flush=True)


def read_page(rd, v, n, width, floor):
    r = get_image(v, n, floor, size=f"{width},")
    if r == "full":
        raise SystemExit(f"disk floor {floor} GB reached")
    img = v.dir / (v.label(n) + ".jpg")
    if not img.exists():
        return ""
    vt = rd.vision(img, v.dir / "ocr" / (img.stem + ".vision.tsv"))
    return rd.trocr(img, vt, v.dir / "ocr" / (img.stem + ".trocr.tsv"))


def locate(root, tag, ids, names, frac, tries, width, floor):
    """Volumes in order (newest first): read whole pages outward from FRAC
    of the numbered pages until a short line names a place; the hit's
    position becomes the start for the next volume (a parish keeps its
    farms in much the same order from book to book)."""
    rd = Reader(root)
    sd = root / "sweep"
    sd.mkdir(exist_ok=True)
    for vid in ids:
        v = volume(root, vid)
        if not v:
            continue
        pg = paged(v)
        c = round(frac * (len(pg) - 1))
        order = [c + d for k in range(tries) for d in ((k + 1) // 2 * (-1 if k % 2 else 1),)]
        found = None
        for i in order:
            if not 0 <= i < len(pg):
                continue
            n = pg[i]
            hits = []
            for line in read_page(rd, v, n, width, floor).splitlines():
                b, rest = line.split("\t", 1)
                t = rest.rsplit("|", 1)[0]
                y = float(b.split()[1])
                # a place heading: top of the page, or "X under Y"; not a person
                # whose surname resembles a place name (a surname scored 0.86 against a farm)
                if len(t.split()) <= 4 and (y < 0.22 or " under " in f" {t.lower()} "):
                    sc, name = score(t, names)
                    if sc >= 0.8:
                        hits.append((name, sc, t))
            print(time.strftime("%T"), vid, n, hits[:3], flush=True)
            if hits:
                with open(sd / f"{tag}.tsv", "a", encoding="utf-8") as o:
                    for name, sc, t in hits:
                        o.write(f"{vid}\t{n}\t{v.label(n)}\t{name}\t{sc:.2f}\t{t}\n")
                found = i
                break
        if found is not None:
            frac = found / (len(pg) - 1)
        print(time.strftime("%T"), vid, "found" if found is not None else "not found",
              f"next frac {frac:.3f}", flush=True)


def wanted(sd, tag, pad):
    """{volume id: images}: the tag's matches and extras, their neighbours
    (PAD) and the gaps between them up to six images."""
    want = {}
    for f in (sd / f"{tag}.tsv", sd / f"{tag}-extra.tsv"):
        if f.exists():
            for l in f.read_text(encoding="utf-8").splitlines():
                p = l.split("\t")
                if len(p) >= 2 and p[1].isdigit():
                    want.setdefault(p[0], set()).add(int(p[1]))
    out = {}
    for vid, ns in want.items():
        s = sorted(ns)
        full = set()
        for a, b in zip(s, s[1:]):
            if b - a <= 6:
                full.update(range(a, b + 1))
        for n in s:
            full.update(range(n - pad, n + pad + 1))
        out[vid] = full
    return out


def pages(root, tag, pad, width, floor):
    rd = Reader(root)
    for vid, full in wanted(root / "sweep", tag, pad).items():
        v = volume(root, vid)
        for n in sorted(full):
            r = get_image(v, n, floor, size=f"{width},")
            if r == "full":
                raise SystemExit(f"disk floor {floor} GB reached")
            img = v.dir / (v.label(n) + ".jpg")
            if not img.exists():
                continue
            vt = rd.vision(img, v.dir / "ocr" / (img.stem + ".vision.tsv"))
            rd.trocr(img, vt, v.dir / "ocr" / (img.stem + ".trocr.tsv"))
            print(time.strftime("%T"), vid, n, r, flush=True)


def report(root, tag, pad):
    for vid, full in wanted(root / "sweep", tag, pad).items():
        v = Vol(root, vid, {})
        if not v.load():
            continue
        md = v.meta()
        print(f"\n# {md.get('Referenskod', vid)} ({md.get('Datering', '')}) {vid}")
        for n in sorted(full):
            t = v.dir / "ocr" / (v.label(n) + ".trocr.tsv") if 0 < n <= len(v.canvases()) else None
            if t and t.exists():
                print(f"\n## {v.label(n)}")
                for line in text_of(t.read_text(encoding="utf-8")):
                    print(line)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2:
        raise SystemExit(__doc__)
    root = Path(opt(a, "--root", MAIN / "data/archive"))
    if (root / "cookie.txt").exists():
        shelf.COOKIE = (root / "cookie.txt").read_text().strip()
    floor = float(opt(a, "--floor-gb", 5))
    cmd, tag = a[0], a[1]
    ids = [x for x in a[2:] if not x.startswith("--") and x not in
           {opt(a, k, None) for k in ("--names", "--step", "--floor-gb", "--root", "--width",
                                      "--pad", "--frac", "--tries")}]
    names = [n.strip() for n in opt(a, "--names", "").split(",") if n.strip()]
    if cmd == "heads":
        heads(root, tag, ids, names, int(opt(a, "--step", 3)), floor)
    elif cmd == "locate":
        locate(root, tag, ids, names, float(opt(a, "--frac", 0.5)), int(opt(a, "--tries", 12)),
               int(opt(a, "--width", 2600)), floor)
    elif cmd == "register":
        register(root, tag, ids, names, int(opt(a, "--width", 2600)), floor)
    elif cmd == "pages":
        pages(root, tag, int(opt(a, "--pad", 1)), int(opt(a, "--width", 2600)), floor)
    elif cmd == "report":
        report(root, tag, int(opt(a, "--pad", 1)))
    else:
        raise SystemExit(__doc__)
