"""Keep archive volumes locally as a human-readable shelf (sketch, unvalidated).

python3 shelf.py fetch [--phases 1,3,4,6] [--floor-gb 15] [--root DIR]
python3 shelf.py index [--root DIR]
python3 shelf.py ocr [--follow] [--root DIR]
python3 shelf.py rush <viewer URL> [--floor-gb 15] [--root DIR]
python3 shelf.py frontmatter [--root DIR]
python3 shelf.py pages [--root DIR]

Volumes come from data/output/volume_refs.csv (ra_images = Riksarkivet
image-series id). Work runs breadth first, one phase over all volumes
before the next, in the order given (default 1,3,4,6: cited
and index pages first; then ocr, frontmatter, fetch --phases 8):
  1 manifest (IIIF v3: page labels, structure = parish/record/years ranges)
  2 images 1, 2 and the last one, full size: not in the default run
    (filming cards and inside covers; the outside and spine are in scout)
  3 cited images (image_no in volume_refs, or a cited page through
    Riksarkivet's page label) and the one after
  4 index pages: canvases in structure ranges named register/index/...
  6 scout, 1000 px wide into scout/: the last three images before the
    first page number (cover, index), and spines (wide images, kept small
    to illustrate the volume)
  8 full size for the scouted images frontmatter.tsv classes as
    index (run `ocr` and `frontmatter` between 6 and 8); covers and
    spines stay at scout size
  7 unpaginated images between numbered pages (registers between books):
    not in the default run
  5 thumbnails (200 px wide), into thumbs/, of the pages between the
    first and last pertinent page (cited or index), a blurry stand-in
    for pages not kept at full size: not in the default run, and
    thumbs/ may be deleted to save space (about 6 kB an image)
Layout under ROOT (default data/archive, git-ignored):
  <Arkiv>/<ref> <serie> (<dates>) <id>/
      manifest.json.gz  volume.md  Bild 0060 - Sida 106.jpg ...
  structure.tsv (public structure only), pending-login.tsv, log.tsv
`ocr` runs Apple Vision (vision.swift, compiled once into ROOT/.bin) on
every full-size image without output yet, writing <volume>/ocr/<image>.vision.tsv
(box x y w h, then three candidates|confidence; untuned, raw). --follow
keeps polling while fetch adds images, and stops after an idle day.
`frontmatter` sorts the unpaginated images that have Vision text into
target (filming cards: BEGIN/BÖRJAN, county and date), cover (few short
lines), index (many lines, most with digits) or other, into
frontmatter.tsv. Rough rules from one example volume, unvalidated.
Rerunnable: existing files are skipped. A 401 marks the volume as
login-only for this run (rest of it skipped) and lists the image in
pending-login.tsv. Polite: one request at a time, ~1/s, Referer as the
viewer sends it (CJ approved fair use, 2026-11-15)."""
import csv
import gzip
import json
import os
import re
import subprocess
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

    def paged(s):
        """{MyHeritage page: image whose Riksarkivet label is that page, or None}.
        Where Riksarkivet labels a spread by its left page only (every other
        number), a page missing between two labels is the right-hand page
        of the image labelled one lower."""
        lab = {}
        for i, c in enumerate(s.canvases(), 1):
            for x in re.findall(r"Sida\s+(\d+)", sv(c["label"])):
                lab.setdefault(int(x), i)
        return {p: lab.get(p) or (lab.get(p - 1) if p + 1 in lab else None)
                for p in PAGED.get(s.id, ())}

    def cited(s):
        """Images cited by number, and by page through Riksarkivet's label."""
        return set(s.cites) | {n for n in s.paged().values() if n}

    def unpaginated(s):
        """(front, inner): image numbers before the first page number, and
        those without one between the first and last numbered page."""
        pg = [i for i, c in enumerate(s.canvases(), 1) if "Sida" in sv(c["label"])]
        if not pg:
            return list(range(1, min(10, len(s.canvases())) + 1)), []
        return (list(range(1, pg[0])),
                [i for i in range(pg[0], pg[-1]) if i not in set(pg)])

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


PAGED = {}   # volume -> Counter of MyHeritage page numbers cited without an image


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
        elif r["page"].isdigit():
            PAGED.setdefault(v, Counter())[int(r["page"])] += 1
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
        tmp = out.with_name(out.name + ".%d.part" % os.getpid())
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


def get_manifest(v):
    code, body = http(f"https://lbiiif.riksarkivet.se/arkis!{v.id}/manifest")
    if code != 200:
        log(v.root, "manifest", v.id, code, body[:80])
        return code
    v.m = json.loads(body)
    v.place()
    (v.dir / "manifest.json.gz").write_bytes(gzip.compress(body))
    return code


def write_volume_md(v, years):
    md = v.meta()
    lines = [f"# {sv(v.m['label'])}", ""]
    lines += [f"- {k}: {val}" for k, val in md.items()]
    lines += [f"- Bilder: {len(v.canvases())}",
              f"- Bildvisning: https://sok.riksarkivet.se/bildvisning/{v.id}",
              f"- Citerade bilder: {', '.join(map(str, sorted(v.cites))) or '-'}",
              "- Citerade sidor utan bild (MyHeritage), bild enligt Riksarkivets"
              f" sidetikett: {', '.join(f'sida {p} → ' + (f'bild {n}' if n else 'ingen etikett') for p, n in sorted(v.paged().items())) or '-'}",
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
                write_volume_md(v, years)   # cited lists change with the tree
                tally["have"] += 1
                continue
            code = get_manifest(v)
            if code != 200:
                tally[f"err{code}"] += 1
                continue
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
                if r != "have" and r != "skip":
                    print(time.strftime("%F %T"), f"phase {ph}", r, v.dir.relative_to(root),
                          f"bild {n}", kw.get("sub", ""), flush=True)
                if r == "full":
                    report(ph)
                    raise SystemExit(f"disk floor {floor} GB reached")
        report(ph)

    def scout(v):
        front = v.unpaginated()[0]
        spines = [n for n in front if is_spine(v, n)]
        return sorted(set(front[-3:]) | set(spines))

    wanted = {}
    if (root / "frontmatter.tsv").exists():
        for l in (root / "frontmatter.tsv").read_text(encoding="utf-8").splitlines()[1:]:
            f = l.split("\t")
            if f[5] == "index":
                wanted.setdefault(f[0], []).append(int(f[2]))

    def between(v):
        keep = v.cited() | set(index_pages(v))
        return range(min(keep), max(keep) + 1) if keep else []

    for ph in phases:   # in the order given
        if ph == 2:
            run(2, lambda v: [1, 2, len(v.canvases())])
        elif ph == 3:
            run(3, lambda v: sorted({m for n in v.cited() for m in (n, n + 1)}))
        elif ph == 4:
            run(4, index_pages)
        elif ph == 5:
            run(5, between, size="200,", sub="thumbs")
        elif ph == 6:
            run(6, scout, size="1000,", sub="scout")
        elif ph == 8:
            run(8, lambda v: wanted.get(v.id, []))
        elif ph == 7:
            run(7, lambda v: v.unpaginated()[1])


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


def vision_exe(root):
    exe = root / ".bin/vision"
    src = Path(__file__).with_name("vision.swift")
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        exe.parent.mkdir(exist_ok=True)
        subprocess.run(["swiftc", "-O", str(src), "-o", str(exe)], check=True)
    return exe


def vision(root, exe, img):
    """Vision text for one image into ocr/; the output path, or None."""
    out = img.parent / "ocr" / (img.stem + ".vision.tsv")
    if out.exists():
        return out
    out.parent.mkdir(exist_ok=True)
    r = subprocess.run([str(exe), str(img)], capture_output=True, text=True)
    if r.returncode:
        log(root, "ocr", img.relative_to(root), r.returncode, r.stderr[:80])
        return None
    tmp = out.with_name(out.name + ".%d.part" % os.getpid())
    tmp.write_text(r.stdout, encoding="utf-8")
    tmp.rename(out)
    return out


def ocr(root, follow):
    exe = vision_exe(root)
    idle = 0
    while True:
        done = 0
        for img in sorted(root.glob("*/*/Bild *.jpg")) + sorted(root.glob("*/*/scout/Bild *.jpg")):
            if (img.parent / "ocr" / (img.stem + ".vision.tsv")).exists():
                continue
            done += vision(root, exe, img) is not None
        print(time.strftime("%F %T"), "ocr", done, flush=True)
        if not follow:
            return
        idle = 0 if done else idle + 1
        if idle >= 144:
            return
        time.sleep(600)


def rush(root, url, floor):
    """One image now, from a viewer link (sok.riksarkivet.se/bildvisning/
    <id>_<n>, or an IIIF arkis!<id>_<n> URL): manifest and volume.md if
    new, the image full size, its Vision text. Stored as fetch and ocr do."""
    m = re.search(r"(?:bildvisning/|arkis!)(\w+?)_(\d+)", url)
    if not m:
        raise SystemExit("no <volume>_<image> in " + url)
    vid, n = m.group(1), int(m.group(2))
    cites, years = read_refs()
    v = Vol(root, vid, cites.get(vid, Counter()))
    if not v.load():
        code = get_manifest(v)
        if code != 200:
            raise SystemExit(f"manifest {vid}: HTTP {code} (401: login, cookie.txt)")
        write_volume_md(v, years)
    r = get_image(v, n, floor)
    img = v.dir / (v.label(n) + ".jpg")
    if not img.exists():
        raise SystemExit(f"bild {n}: {r} (see log.tsv)")
    out = vision(root, vision_exe(root), img)
    print(r, img.relative_to(root))
    if out:
        print(len(out.read_text(encoding="utf-8").splitlines()), "lines:", out.relative_to(root))


TARGET_RE = re.compile(r"\b(BEGIN|BÖRJAN|BORJAN|SLUT|END|FORTS|KONTROLL)\b|LÄN\b|\b(JAN|FEB|MAR|APR|MAY|MAJ|JUN|JUL|AUG|SEP|OCT|OKT|NOV|DEC) \d{1,2},? \d{4}")
CARD_RE = re.compile(r"\bSVAR\b|exponering|\bfax\b|\btel:|volymnummer|kamera:|imagelink|riksarkivet|skannad av", re.I)
FORM_RE = re.compile(r"barnhus|folkmängd|kassor|förvaltare", re.I)
TITLE_RE = re.compile(r"församlingsbok|husförhörs|\bbok\b", re.I)


def is_spine(v, n):
    c = v.canvases()[n - 1]
    return c.get("width", 0) > 2.5 * max(1, c.get("height", 1))


def classify(lines):
    """Vision lines [(x, y, w, h, text)] of an unpaginated image -> kind."""
    text = " ".join(t for *_, t in lines)
    hs = sorted(h for _, _, _, h, _ in lines)
    dig = sum(any(ch.isdigit() for ch in t) for *_, t in lines)
    if TARGET_RE.search(text) or CARD_RE.search(text) or (hs and hs[-1] > 0.3):
        return "target"
    if FORM_RE.search(text):
        return "form"
    if TITLE_RE.search(" ".join(t for *_, t in lines[:3])) and len(lines) <= 12:
        return "cover"
    if len(lines) >= 15 and dig >= 0.4 * len(lines):
        return "index"
    if 1 <= len(lines) <= 6:
        return "cover"
    return "other" if lines else "blank"


def frontmatter(root):
    cites, years = read_refs()
    rows = []
    for vid in cites:
        v = Vol(root, vid, cites[vid])
        if not v.load():
            continue
        front, inner = v.unpaginated()
        for n in front + inner:
            tsv = v.dir / "ocr" / (v.label(n) + ".vision.tsv")
            if not tsv.exists():
                tsv = v.dir / "scout" / "ocr" / (v.label(n) + ".vision.tsv")
            if not tsv.exists():
                continue
            lines = []
            for l in tsv.read_text(encoding="utf-8").splitlines():
                b, _, c = l.partition("\t")
                lines.append((*map(float, b.split()), c.split("|")[0]))
            top = " / ".join(t for *_, t in sorted(lines, key=lambda x: -x[3])[:3])
            rows.append([vid, v.meta().get("Referenskod", ""), str(n),
                         "front" if n in front else "inner", str(len(lines)),
                         "spine" if is_spine(v, n) else classify(lines), top.replace("\t", " ")])
    with open(root / "frontmatter.tsv", "w", encoding="utf-8") as o:
        o.write("volume\treference\timage\twhere\tlines\tkind\ttop text\n")
        o.writelines("\t".join(r) + "\n" for r in rows)
    print(Counter(r[5] for r in rows))


def read_numbers(tsv):
    """Numbers in the outer top corners of a page, years left out:
    [(number, left half?)]."""
    out = []
    for line in open(tsv, encoding="utf-8"):
        box, _, text = line.rstrip("\n").partition("\t")
        x, y, w, h = map(float, box.split())
        cx = x + w / 2
        if y < 0.12 and (cx < 0.2 or cx > 0.8):
            for m in re.findall(r"\b\d{1,4}\b", text.split("  ")[0].rsplit("|", 1)[0]):
                if not 1500 <= int(m) <= 2000:
                    out.append((int(m), cx < 0.5))
    return out


def pages(root):
    """pages.tsv: the page number written on each held image, fitted per
    volume from the numbers read in the top band. Each number votes for a
    line page = k * image + b (k 1 for one page an image, 2 for a spread,
    left page from the left half); runs of two or more images that agree
    win, so a single misreading is outvoted. Images between a run's first
    and last image get the fitted number even when nothing was read, from
    the strongest run, but never a page number a run read on another image."""
    rows = []
    for vd in sorted(p for p in root.glob("*/*") if (p / "manifest.json.gz").exists()):
        seen = {}
        for tsv in list(vd.glob("ocr/Bild *.vision.tsv")) + list(vd.glob("scout/ocr/Bild *.vision.tsv")):
            n = int(re.match(r"Bild (\d+)", tsv.name).group(1))
            m = re.search(r"Sida (\d+)", tsv.name)
            if n not in seen or tsv.parent.parent == vd:
                seen[n] = (m and int(m.group(1)), read_numbers(tsv))
        votes = {}
        for n, (_, nums) in seen.items():
            for c, left in nums:
                for k in (1, 2):
                    b = c - k * n - (0 if k == 1 or left else 1)
                    votes.setdefault((k, b), set()).add(n)
        runs, used = [], set()
        for (k, b), imgs in sorted(votes.items(), key=lambda kv: -len(kv[1])):
            imgs = imgs - used
            if len(imgs) < 2:
                break
            runs.append((k, b, imgs))
            used |= imgs
        # page -> the image it was read on, in a run or as Riksarkivet's label
        held = {k * i + b: i for k, b, imgs in reversed(runs) for i in imgs}
        confirmed = {i: lab for i, (lab, nums) in seen.items() if lab and any(c == lab for c, _ in nums)}
        held.update({lab: i for i, lab in confirmed.items()})

        def spans(k, b, imgs, n):
            """n is read in the run, or no confirmed label between the run's
            images either side of n contradicts the run."""
            if n in imgs:
                return True
            lo, hi = max(i for i in imgs if i < n), min(i for i in imgs if i > n)
            return not any(lo < m < hi and lab not in (k * m + b, k * m + b + k - 1)
                           for m, lab in confirmed.items())

        for n in sorted(seen):
            label, nums = seen[n]
            # the strongest run spanning n, unless its page was read on another image
            fit = [(k, b, imgs) for k, b, imgs in runs if min(imgs) <= n <= max(imgs)][:1]
            fit = [(k, b) for k, b, imgs in fit if spans(k, b, imgs, n)
                   and (n in imgs or held.get(k * n + b, n) == n)]
            page, verdict = "", "unread"
            if label and any(c == label for c, _ in nums):
                page, verdict = str(label), "agrees"
            elif fit:
                k, b = fit[0]
                page = str(k * n + b) + ("-%d" % (k * n + b + 1) if k == 2 else "")
                first = k * n + b
                read = any(c in (first, first + k - 1) for c, _ in nums)
                verdict = ("no label" if not label else "agrees" if label in (first, first + k - 1)
                           else "label differs") + \
                          ("" if read else ", fitted")
            elif nums:
                verdict = "read, no run"
            rows.append((vd.name.rsplit(" ", 1)[-1], n, label or "", page, verdict,
                         " ".join(str(c) for c, _ in nums[:6])))
    with open(root / "pages.tsv", "w", encoding="utf-8") as o:
        o.write("volume\timage\tra_label\twritten\tverdict\tnumbers_read\n")
        o.writelines("\t".join(map(str, r)) + "\n" for r in rows)
    print(Counter(r[4] for r in rows))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in ("fetch", "rush", "index", "ocr", "frontmatter", "pages"):
        raise SystemExit(__doc__)

    def opt(k, d):
        return a[a.index(k) + 1] if k in a else d
    root = Path(opt("--root", MAIN / "data/archive"))
    root.mkdir(parents=True, exist_ok=True)
    if (root / "cookie.txt").exists():
        COOKIE = (root / "cookie.txt").read_text().strip()
    if a[0] == "rush":
        rush(root, a[1], float(opt("--floor-gb", "15")))
    elif a[0] == "index":
        index(root)
    elif a[0] == "frontmatter":
        frontmatter(root)
    elif a[0] == "pages":
        pages(root)
    elif a[0] == "ocr":
        ocr(root, "--follow" in a)
    else:
        fetch(root, [int(x) for x in opt("--phases", "1,3,4,6").split(",")],
              float(opt("--floor-gb", "15")))
