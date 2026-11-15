"""Keep archive volumes locally as a human-readable shelf (sketch, unvalidated).

python3 shelf.py fetch [--phases 1,2,3,4,5] [--floor-gb 15] [--root DIR]
python3 shelf.py index [--root DIR]

Volumes come from data/output/volume_refs.csv (ra_images = Riksarkivet
image-series id). Work runs breadth first, one phase over all volumes
before the next:
  1 manifest (IIIF v3: page labels, structure = parish/record/years ranges)
  2 covers: images 1, 2 and the last one
  3 cited images (image_no in volume_refs) and the one after
  4 index pages: canvases in structure ranges named register/index/...
  5 thumbnails (200 px wide), into thumbs/, of the pages between the
    first and last pertinent page (cited or index), a blurry stand-in
    for pages not kept at full size (CJ, 2026-11-15)
Layout under ROOT (default data/archive, git-ignored):
  <Arkiv>/<ref> <serie> (<dates>) <id>/
      manifest.json.gz  volume.md  Bild 0060 - Sida 106.jpg ...
  structure.tsv (public structure only), pending-login.tsv, log.tsv
Rerunnable: existing files are skipped. A 401 marks the volume as
login-only for this run (rest of it skipped) and lists the image in
pending-login.tsv. Polite: one request at a time, ~1/s, Referer as the
viewer sends it (CJ approved fair use, 2026-11-15)."""
import csv
import gzip
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

MAIN = Path(__file__).resolve().parents[2]
while not (MAIN / "data/output").exists() and MAIN.parent != MAIN:
    MAIN = MAIN.parent  # a worktree: use the main checkout's data/
REFS = MAIN / "data/output/volume_refs.csv"
HDR = {"Referer": "https://sok.riksarkivet.se/",
       "User-Agent": "synthetic-genealogy/0.1 (personal archive copy)"}
INDEX_RE = re.compile(r"regist|index|innehåll|förteckn|alfabet", re.I)
COOKIE = None  # set from ROOT/cookie.txt if present (login, later)


def http(url, tries=6):
    h = dict(HDR)
    if COOKIE:
        h["Cookie"] = COOKIE
    for t in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h),
                                        timeout=90) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                return e.code, b""
            err = e
        except Exception as e:  # flaky 4G: back off and retry
            err = e
        time.sleep(min(300, 5 * 2 ** t))
    return 0, str(err).encode()


def sv(x):
    if isinstance(x, dict):
        for k in ("sv", "none", "en"):
            if k in x:
                return " ".join(x[k])
    return str(x)


def safe(s):
    return re.sub(r"[/:\\]", " ", s).strip()


class Vol:
    def __init__(s, root, vid, cites):
        s.root, s.id, s.cites = root, vid, cites
        s.m = None
        s.dir = None
        s.login = False

    def load(s):
        hit = list(s.root.glob(f"*/* {s.id}/manifest.json.gz"))
        if hit:
            s.dir = hit[0].parent
            s.m = json.loads(gzip.decompress(hit[0].read_bytes()))
        return s.m

    def meta(s):
        return {sv(d["label"]): sv(d["value"]) for d in s.m.get("metadata", [])}

    def place(s):
        md = s.meta()
        ref = md.get("Referenskod", "")
        tail = " ".join(ref.split("/")[3:]) or ref
        name = f"{tail} {md.get('Serie', '')} ({md.get('Datering', '')}) {s.id}"
        s.dir = s.root / safe(md.get("Arkiv", "okänt arkiv")) / safe(re.sub(r"\s+", " ", name))
        s.dir.mkdir(parents=True, exist_ok=True)

    def canvases(s):
        return s.m["items"]

    def label(s, n):
        lab = sv(s.canvases()[n - 1]["label"])
        m = re.search(r"Sida\s+(\S+)", lab)
        return f"Bild {n:04d}" + (f" - Sida {safe(m.group(1))}" if m else "")

    def ranges(s):
        """Yield (path labels, first image, last image) for leaf ranges."""
        def walk(r, path):
            kids = [i for i in r.get("items", []) if i["type"] == "Range"]
            cans = [int(re.search(r"_(\d+)/canvas", i["id"]).group(1))
                    for i in r.get("items", []) if i["type"] == "Canvas"]
            p = path + [sv(r["label"])]
            if cans:
                yield p, min(cans), max(cans)
            for k in kids:
                yield from walk(k, p)
        for r in s.m.get("structures", []):
            yield from walk(r, [])


def read_refs():
    cites, years = {}, {}
    for r in csv.DictReader(open(REFS, encoding="utf-8")):
        v = r["ra_images"]
        if not v:
            continue
        cites.setdefault(v, Counter())
        years[v] = r["ra_years"]
        if r["image_no"].isdigit():
            cites[v][int(r["image_no"])] += 1
    tsv = MAIN / "data/cache/iiif/volumes.tsv"  # volumes opened by hand
    if tsv.exists():
        for r in csv.DictReader(open(tsv, encoding="utf-8"), delimiter="\t"):
            v = r["volume"]
            years.setdefault(v, (re.findall(r"1[5-9]\d\d", r["reference"]) or ["0"])[-1])
            cites.setdefault(v, Counter())
            if r["image"].isdigit():
                cites[v][int(r["image"])] += 1
    return cites, years


def log(root, *f):
    with open(root / "log.tsv", "a", encoding="utf-8") as o:
        o.write("\t".join(map(str, (time.strftime("%F %T"),) + f)) + "\n")


def free_gb(root):
    return shutil.disk_usage(root).free / 1e9


def get_image(v, n, floor, size="full", sub=""):
    if v.login or n < 1 or n > len(v.canvases()):
        return "skip"
    name = v.label(n) + ".jpg"
    out = v.dir / sub / name if sub else v.dir / name
    if sub and (v.dir / name).exists():
        return "have"
    out.parent.mkdir(exist_ok=True)
    if out.exists():
        return "have"
    if free_gb(v.root) < floor:
        return "full"
    url = f"https://lbiiif.riksarkivet.se/v2/arkis!{v.id}_{n:05d}/full/{size}/0/default.jpg"
    code, body = http(url)
    if code == 200 and body[:2] == b"\xff\xd8":
        tmp = out.with_suffix(".part")
        tmp.write_bytes(body)
        tmp.rename(out)
        time.sleep(1.0 if size == "full" else 0.5)
        return "got"
    if code == 401:
        v.login = True
        with open(v.root / "pending-login.tsv", "a", encoding="utf-8") as o:
            o.write(f"{v.id}\t{n}\t{v.dir.relative_to(v.root)}\n")
    log(v.root, "img", v.id, n, code, body[:80])
    time.sleep(1.0)
    return f"err{code}"


def write_volume_md(v, years):
    md = v.meta()
    lines = [f"# {sv(v.m['label'])}", ""]
    lines += [f"- {k}: {val}" for k, val in md.items()]
    lines += [f"- Bilder: {len(v.canvases())}",
              f"- Bildvisning: https://sok.riksarkivet.se/bildvisning/{v.id}",
              f"- Citerade bilder: {', '.join(map(str, sorted(v.cites))) or '-'}",
              "", "## Innehåll (struktur från Riksarkivet)", ""]
    for p, a, b in v.ranges():
        lines.append(f"- {' / '.join(p)}: bild {a}–{b}")
    (v.dir / "volume.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def fetch(root, phases, floor):
    cites, years = read_refs()
    # public volumes first within each phase; login-only ones after
    order = sorted(cites, key=lambda v: (years[v][-4:] >= "1916", -sum(cites[v].values())))
    vols = [Vol(root, v, cites[v]) for v in order]
    tally = Counter()

    def report(ph):
        print(f"phase {ph}: {dict(tally)}", flush=True)
        log(root, "phase", ph, dict(tally))
        tally.clear()

    if 1 in phases:
        for v in vols:
            if v.load():
                tally["have"] += 1
                continue
            code, body = http(f"https://lbiiif.riksarkivet.se/arkis!{v.id}/manifest")
            if code != 200:
                log(root, "manifest", v.id, code, body[:80])
                tally[f"err{code}"] += 1
                continue
            v.m = json.loads(body)
            v.place()
            (v.dir / "manifest.json.gz").write_bytes(gzip.compress(body))
            write_volume_md(v, years)
            tally["got"] += 1
            time.sleep(1.0)
        report(1)
        write_structure(root, vols)
    vols = [v for v in vols if v.m or v.load()]

    def run(ph, pick, **kw):
        for v in vols:
            for n in pick(v):
                r = get_image(v, n, floor, **kw)
                tally[r] += 1
                if r == "full":
                    report(ph)
                    raise SystemExit(f"disk floor {floor} GB reached")
        report(ph)

    if 2 in phases:
        run(2, lambda v: [1, 2, len(v.canvases())])
    if 3 in phases:
        run(3, lambda v: sorted({m for n in v.cites for m in (n, n + 1)}))
    if 4 in phases:
        run(4, index_pages)
    if 5 in phases:
        def between(v):
            keep = set(v.cites) | set(index_pages(v))
            return range(min(keep), max(keep) + 1) if keep else []
        run(5, between, size="200,", sub="thumbs")


def index_pages(v):
    return [n for p, a, b in v.ranges() if INDEX_RE.search(" ".join(p))
            for n in range(a, b + 1)]


def write_structure(root, vols):
    with open(root / "structure.tsv", "w", encoding="utf-8") as o:
        o.write("volume\treference\tarchive\tseries\tdates\timages\tsection\tfirst\tlast\n")
        for v in vols:
            if not v.m:
                continue
            md = v.meta()
            base = [v.id, md.get("Referenskod", ""), md.get("Arkiv", ""),
                    md.get("Serie", ""), md.get("Datering", ""), str(len(v.canvases()))]
            rs = list(v.ranges()) or [([], "", "")]
            for p, a, b in rs:
                o.write("\t".join(base + [" / ".join(p), str(a), str(b)]) + "\n")


def index(root):
    cites, years = read_refs()
    vols = [Vol(root, v, cites[v]) for v in cites]
    vols = [v for v in vols if v.load()]
    write_structure(root, vols)
    rows = ["# Arkivhylla", "", "| Arkiv | Volym | Bilder | Hämtade |", "|---|---|---|---|"]
    for v in sorted(vols, key=lambda v: str(v.dir)):
        got = len(list(v.dir.glob("Bild *.jpg")))
        rel = v.dir.relative_to(root)
        rows.append(f"| {rel.parts[0]} | [{rel.parts[1]}](<{rel}/volume.md>) | {len(v.canvases())} | {got} |")
    (root / "README.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(len(vols), "volumes indexed")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in ("fetch", "index"):
        raise SystemExit(__doc__)

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d
    root = Path(opt("--root", MAIN / "data/archive"))
    root.mkdir(parents=True, exist_ok=True)
    if (root / "cookie.txt").exists():
        COOKIE = (root / "cookie.txt").read_text().strip()
    if a[0] == "index":
        index(root)
    else:
        fetch(root, {int(x) for x in opt("--phases", "1,2,3,4,5").split(",")},
              float(opt("--floor-gb", "15")))
