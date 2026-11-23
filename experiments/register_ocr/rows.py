"""The cited people's rows on the shelf: moves and remarks (sketch, unvalidated).

python3 rows.py [ROOT] [--person MH:ID]   (ROOT: the shelf, default data/archive)

Text only: works on the line files the shelf already holds (Vision's
ocr/<image>.vision.tsv, TrOCR's .trocr.tsv on the same boxes, cells.py's
.cols.tsv where read_pages ran) and reads no image. For each citation in
volume_refs.csv on a page with line files:

- columns: printed headers in the top quarter name them (HEADERS below);
  a kind the page lacks comes from the volume's other pages (where it
  stands on three or more); each line goes to the nearest header by x;
- the person's rows: everyone cited on the page is placed at once; each
  line in the name column goes to the person whose name and birth (the
  birth against the tree's, read on the same height) it fits best, and a
  person keeps every line won at score 0.9 or more (one who left and came
  back stands in two rows), else their best line, as unsure. A row runs
  from halfway up to the previous name (a note starts above the name)
  down to the next name;
- every line in that row by column. Moved in/out are parsed into year and
  parish (cells.py's cells where they exist, else the lines); anything in
  another column than name, birth, moves, death, marriage or occupation is
  a remark (lyte, frejd, notes, reading, communion, vaccination, military,
  guardian; a line in the name column is a name, not a remark), as is
  any line with a word from WORDS (sinnessjuk, fattighjon,
  hospital, ...), fuzzily, in whichever column (on a page with no headers
  found, only those). A move to America is 'abroad'.

Writes data/output/moves_read.tsv and remarks_read.tsv (the Family view's
hints) for rows found with score >= 0.9, and data/cache/rows/rows.tsv
(every citation tried); prints the flagged remarks. Rerun any time.
--person prints that person's rows and writes nothing.
Man page: docs/man/rows.1.md."""
import csv
import difflib
import glob
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).parent))
import shelf  # noqa: E402

MAIN = shelf.MAIN

# printed headers, loosely (Vision misreads print: "fräjd", "Jutlytad", "bivistat")
HEADERS = {
    "in": r"(hit|in|ink)fl[iy]?[tl]+ad|^inflytt|^hitkom",
    "out": r"(bort|ut|jut)fl[iy]?[tl]+ad|utfl[iy]?t",
    "name": r"\bnamn\b|personernas|personens för",
    "born": r"födelse|\bfödd?e?\b",
    "died": r"^död\b|dödsår|^död\.",
    "marriage": r"äktenskap|aktenskap|\bgift\b",
    "occupation": r"\byrke|embete",
    "lyte": r"\blyte|blinda|döfstum|dövstum|sinnessjuk|svagsint",
    "frejd": r"fr[äe]jd",
    "notes": r"anteckning|anmärkning|omständighet",
    "reading": r"\bläser|\blässer|cateches|katekes|kunskap",
    "communion": r"nattvard|b[ie]vistat|förhör",
    "vaccination": r"koppor|vaccin",
    "military": r"värnplikt",
    "guardian": r"omyndig|förmyndar",
}
MAIN_COLS = {"name", "born", "in", "out", "died", "marriage", "occupation"}

# words worth a flag wherever they stand: stem -> label
WORDS = {
    "sinnessjuk": "sinnessjuk", "sinnesslö": "sinnesslö", "svagsint": "svagsint", "idiot": "idiot",
    "blind": "blind", "döfstum": "dövstum", "dövstum": "dövstum", "krympling": "krympling",
    "vanför": "vanför", "ofärdig": "ofärdig", "fallandesot": "fallandesot", "epilept": "epilepsi",
    "hospital": "hospital", "asyl": "asyl", "sjukhus": "sjukhus", "sjuklig": "sjuklig",
    "fattighjon": "fattighjon", "fattig": "fattig", "inhyses": "inhyses", "understöd": "understöd",
    "oäkta": "oäkta", "straffad": "straffad", "fängelse": "fängelse", "dömd": "dömd",
    "rannsak": "rannsakad", "lösdrif": "lösdrivare", "lösdriv": "lösdrivare", "stöld": "stöld",
    "tjufnad": "stöld", "kyrkoplikt": "kyrkoplikt", "obefintlig": "obefintlig", "emigr": "emigrerad",
    "omyndig": "omyndig", "förmyndare": "förmyndare",
    "hittebarn": "hittebarn", "barnhus": "barnhusbarn", "fosterbarn": "fosterbarn",
    "utskrif": "utskriven", "utskriv": "utskriven", "intagen": "intagen", "intagit": "intagen",
}


def words(text):
    """Labels from WORDS found in a text: a token that starts with a stem,
    or is close to one (TrOCR's 'vinnesjuk' for 'sinnessjuk')."""
    found = []
    for t in re.findall(r"[a-zåäöü]+", text.lower()):
        if len(t) < 4:
            continue
        for stem, lab in WORDS.items():
            if lab in found:
                continue
            if t.startswith(stem) or (lab == "sinnessjuk" and len(t) >= 7 and t.endswith("sjuk")) or (len(t) >= 6 and len(stem) >= 6 and
                                      difflib.SequenceMatcher(None, t[:len(stem) + 1], stem).ratio() >= 0.8):
                found.append(lab)
    return found


# ---- line files

def read_lines(vision):
    """[(x, y, w, h, text, alt)]: TrOCR's text where it read the box, Vision's as alt."""
    def load(p):
        out = {}
        if Path(p).exists():
            for l in open(p, encoding="utf-8"):
                box, _, t = l.rstrip("\n").partition("\t")
                out[box] = t.split("  ")[0].rsplit("|", 1)[0].strip()
        return out
    v, t = load(vision), load(vision.replace(".vision.", ".trocr."))
    return [(*map(float, b.split()), t.get(b) or v[b], v[b] if b in t else "") for b in v]


def page_heads(lines, top=0.25):
    """[(kind, x centre, y bottom)] from printed headers in the top of the page."""
    out = []
    for x, y, w, h, t, alt in lines:
        if y > top:
            continue
        for k, rx in HEADERS.items():
            if re.search(rx, alt or t, re.I) or re.search(rx, t, re.I):
                out.append((k, x + w / 2, y + h))
                break
    return out


_VOL = {}


def volume_heads(vdir):
    """{kind: [x]} where a header stands on three pages or more (x rounded to 0.03)."""
    if vdir not in _VOL:
        seen = defaultdict(Counter)
        for p in glob.glob(f"{vdir}/ocr/*.vision.tsv"):
            for k, x, _ in set((k, round(x / 0.03) * 0.03, 0) for k, x, _ in page_heads(read_lines(p))):
                seen[k][x] += 1
        _VOL[vdir] = {k: [x for x, n in c.items() if n >= 3] for k, c in seen.items()}
    return _VOL[vdir]


def columns(lines, vdir):
    """[(kind, x centre)] for the page: its own headers, then the volume's
    for kinds it lacks."""
    own = page_heads(lines)
    cols = [(k, x) for k, x, _ in own]
    have = {k for k, _ in cols}
    for k, xs in volume_heads(vdir).items():
        if k not in have:
            cols += [(k, x) for x in xs]
    return cols, max((y for *_, y in own), default=0.12)


def kind_of(line, cols):
    x, y, w, h = line[:4]
    cx = x + min(w, 0.08) / 2
    return min(cols, key=lambda c: abs(c[1] - cx))[0] if cols else "?"


# ---- the person's row (name and birth scoring as the migration review had them)

MON = dict(jan=1, feb=2, mar=3, apr=4, maj=5, jun=6, jul=7, aug=8, sep=9, okt=10, nov=11, dec=12)


def birth(r):
    m = re.match(r"(\d{1,2}) (\w{3}) (\d{4})", r["born"] or "")
    if m:
        return int(m.group(3)), MON.get(m.group(2)), int(m.group(1))
    m = re.search(r"✻\D*(\d{4})", r["label"])
    return (int(m.group(1)), None, None) if m else None


def name_score(name, t):
    toks = [x for x in re.findall(r"\w+", name.lower()) if len(x) > 2]
    tt = re.findall(r"\w+", t.lower())
    return sum(max((difflib.SequenceMatcher(None, a, b).ratio() for b in tt), default=0) for a in toks) / max(1, len(toks))


def given_ok(name, t):
    """A given name read on the line (the surname alone is too common)."""
    giv = [x for x in re.findall(r"\w+", name.lower()) if len(x) > 2][:-1]
    tt = re.findall(r"\w+", t.lower())
    return not giv or any(difflib.SequenceMatcher(None, a, b).ratio() >= 0.75 for a in giv for b in tt)


def birth_score(b, t):
    if not b:
        return 0
    y, mo, d = b
    nums = [int(x) for x in re.findall(r"\d+", t)]
    s = 0.5 if (y in nums or y % 100 in nums) else 0
    return s + (0.3 if d and d in nums and (not mo or mo in nums) else 0)


def name_lines(lines, cols, y0):
    """(body lines, those in the name column)."""
    nx = [x for k, x in cols if k == "name"]
    body = [l for l in lines if l[1] > y0 and l[3] < 0.08]

    def in_name(l):
        cx = l[0] + l[2] / 2
        return abs(cx - nx[0]) < 0.15 if nx else cx < 0.35
    return body, [l for l in body if in_name(l)]


def line_score(body, l, name, b):
    """The name fuzzily (each token's closest reading; a given name
    required) plus the birth read on the same height: partial readings
    still score, the threshold is the caller's. None without a given name."""
    if not given_ok(name, l[4]):
        return None
    mid = l[1] + l[3] / 2
    same = " ".join(o[4] for o in body if abs(o[1] + o[3] / 2 - mid) < 0.6 * l[3] and o is not l)
    return name_score(name, l[4]) + birth_score(b, same + " " + l[4])


def row_of(body, names, l):
    """The lines of the row whose name line is l: from halfway up to the
    previous name line (a note starts at the top of the ruled cell, above
    the name) down to the next name line starting in the same place."""
    prev = [o[1] + o[3] / 2 for o in names if abs(o[0] - l[0]) < 0.06 and o[1] < l[1] - 0.7 * l[3]]
    nxt = [o[1] for o in names if abs(o[0] - l[0]) < 0.1 and o[1] > l[1] + 0.7 * l[3]]   # indented children too
    mid = l[1] + l[3] / 2
    top = min(max((max(prev) + mid) / 2 if prev else 0, l[1] - 0.04), l[1] - 0.3 * l[3])
    bot = max(min(min(nxt, default=1), l[1] + 0.08), l[1] + 1.2 * l[3])
    return [o for o in body if top <= o[1] + o[3] / 2 < bot]


def cols_cells(vision, l):
    """cells.py's in/out cells on the name line's height, if it read the page."""
    p = vision.replace(".vision.tsv", ".cols.tsv")
    if not Path(p).exists():
        return {}
    for row in open(p, encoding="utf-8"):
        if row.startswith("#"):
            continue
        box, *cs = row.rstrip("\n").split("\t")
        x, y, w, h = map(float, box.split())
        if abs((y + h / 2) - (l[1] + l[3] / 2)) < 0.6 * max(h, l[3]):
            return {k: v for k, v in (c.split("=", 1) for c in cs if "=" in c) if k in ("in", "out")}
    return {}


# ---- places in a move (the gazetteer's parishes, abbreviations expanded)

NAMES = {}
for r in csv.DictReader(open(Path(__file__).parents[2] / "gazetteer/parish_names.tsv", encoding="utf-8"), delimiter="\t"):
    for x in [r["label"]] + [a for a in r["aliases"].split("|") if a]:
        m = re.match(r"(.+?)s? (lands|stads)?(församling|socken)$", x.strip())
        base = (m.group(1) if m else x.strip()).lower()
        if len(base) >= 3:
            NAMES.setdefault(base, r["label"])
            w = base.split()
            if len(w) == 2 and w[0].endswith("s") and len(w[1]) >= 5 and w[1] not in ("norra", "södra", "östra", "västra"):
                NAMES.setdefault(w[1], r["label"])          # "jönköpings sofia" -> "sofia"
KEYS = list(NAMES)
ABBR = [(r"\bv\.\s*", "västra "), (r"\bö\.\s*", "östra "), (r"\bn\.\s*", "norra "), (r"\bs\.\s*", "södra "),
        (r"\b(sct|st|s:t|s:t\.)\s*", "s:t "), (r"\bl\.\s*", "lilla ")]
INTERNAL = re.compile(r"\b(fol|pag|p)\b\.?\s*\d+|\bn\.?\s?b\b|\bg\.?\s?b\b|\bf\.?\s?b\b", re.I)
FARM = re.compile(r"(gård|gården|backen|stugan|hult|näs|holm)$")   # farm endings, unless a parish by that name
HEADER = re.compile(r"boken [öo]f?ver|eller månad|överförd|öfverförd|boken över|obefintl|uppslag|år, dag", re.I)


def place(t):
    t = t.lower()
    for a, b in ABBR:
        t = re.sub(a, b, t)
    w = re.findall(r"[a-zåäöé:]+", t)
    best = (None, 0)
    for n in (2, 1):
        for i in range(len(w) - n + 1):
            s = " ".join(w[i:i + n])
            if len(s) < 4 or (FARM.search(s) and s not in NAMES):
                continue
            m = difflib.get_close_matches(s, KEYS, n=1, cutoff=0.82 if len(s) >= 8 else 0.88)
            if m:
                sc = difflib.SequenceMatcher(None, s, m[0]).ratio()
                if sc > best[1]:
                    best = (NAMES[m[0]], sc)
    return best[0]


def year(t, span):
    a, b = span
    for x in re.findall(r"\b\d{2,4}\b", t):
        y = int(x)
        if y < 100:
            for c in (a // 100 * 100, b // 100 * 100):
                if a - 1 <= c + y <= b + 1:
                    return c + y
        elif a - 1 <= y <= b + 1:
            return y
    return None


def move(t, span, known):
    t = "" if HEADER.search(t) else t.strip()
    lab, y = place(t), year(t, span)
    abroad = re.search(r"amer|amwic|amenik", t.lower())
    if abroad and not lab:
        lab = "Nordamerika"
    if not re.search(r"[a-zåäö0-9]{2}", t.lower()):
        v = "empty"
    elif INTERNAL.search(t) and not lab:
        v = "within the book"
    elif abroad:
        v = "abroad"
    elif lab:
        base = re.sub(r"s? (lands|stads)?(församling|socken)$", "", lab.lower())
        v = "known" if any(base in p or p in base for p in known) else "new"
    else:
        v = "unread"
    return dict(text=t, place=lab or "", year=y or "", verdict=v)


# ---- the pass

GOOD = 0.9   # a row counts as the person's from this score


def read_row(r, n, s, nl, name, row, cols, vision, known, names=()):
    """The person's row by column: moves parsed, remarks kept."""
    ys = re.findall(r"\d{4}", r["years"] or "")
    span = (int(ys[0]), int(ys[-1])) if ys else (1600, 2000)
    cells = cols_cells(vision, nl)
    by = defaultdict(list)
    for l in row:
        if l is not nl:
            by[kind_of(l, cols)].append(l)
    res = dict(mh_id=r["mh_id"], name=name, volume=r["volume"], years=r["years"], page=r["page"], image=n,
               score=round(s, 2), name_read=nl[4], headers=" ".join(sorted({k for k, _ in cols})),
               moves=[], remarks=[])
    for k in ("in", "out"):
        t = cells.get(k) or " ".join(l[4] for l in by.get(k, []))
        res["moves"].append(dict(dir=k, **move(t, span, known)))
    for k, ls in by.items():
        for l in ls:
            if HEADER.search(l[4]) or HEADER.search(l[5]):
                continue                   # printed header text read into the row
            flag = words(l[4] + " " + l[5])
            if (k not in MAIN_COLS | {"?"} and l not in names and len(re.findall(r"[a-zåäöA-ZÅÄÖ]", l[4])) >= 3) or flag:
                res["remarks"].append(dict(column=k, flag=" ".join(flag), text=l[4], alt=l[5]))
    return res


def main(root, only=None):
    refs = list(csv.DictReader(open(shelf.REFS, encoding="utf-8")))
    known = defaultdict(set)
    for r in refs:
        for p in (r["parish"], r["event_place"]):
            if p:
                known[r["mh_id"]].add(p.lower())
    cites, _ = shelf.read_refs()
    vols, seen, pages = {}, set(), defaultdict(list)
    for r in refs:
        vid = r["ra_images"]
        if not vid or not r["mh_id"]:
            continue
        if vid not in vols:
            v = shelf.Vol(root, vid, cites.get(vid, {}))
            vols[vid] = v if v.load() else None
        v = vols[vid]
        if not v:
            continue
        n = int(r["image_no"]) if r["image_no"].isdigit() else (v.paged().get(int(r["page"])) if r["page"].isdigit() else None)
        if n and (r["mh_id"], vid, n) not in seen:
            seen.add((r["mh_id"], vid, n))
            pages[(vid, n)].append(r)
    out = []
    for (vid, n), rs in pages.items():
        if only and only not in {r["mh_id"] for r in rs}:
            continue
        f = glob.glob(f"{vols[vid].dir}/ocr/Bild {n:04d}*.vision.tsv")
        if not f:
            continue
        lines = read_lines(f[0])
        cols, y0 = columns(lines, vols[vid].dir)
        body, names = name_lines(lines, cols, y0)
        who = [(r, re.sub(r"\(.*?\)|MH:\S+|✻.*|†.*", "", r["label"]).strip()) for r in rs]
        # everyone cited on the page at once: each name line goes to the
        # person it fits best, so a namesake cannot claim another's row; a
        # person keeps every line won at GOOD or more (someone who left and
        # came back stands in two rows), else their best line, as unsure
        won, best = defaultdict(list), {}
        for l in names:
            sc = [(s, i) for i, (r, nm) in enumerate(who) if (s := line_score(body, l, nm, birth(r))) is not None]
            for s, i in sc:
                if i not in best or s > best[i][0]:
                    best[i] = (s, l)
            if sc:
                s, i = max(sc)
                if s >= GOOD:
                    won[i].append((s, l))
        for i, (r, nm) in enumerate(who):
            if only and r["mh_id"] != only:
                continue
            for s, l in won.get(i) or ([best[i]] if i in best else []):
                out.append(read_row(r, n, s, l, nm, row_of(body, names, l), cols, f[0], known[r["mh_id"]], names))
    if only:                           # one person: print, write nothing
        for x in out:
            print(x["volume"], "p.", x["page"], "score", x["score"], repr(x["name_read"]), "|", x["headers"])
            for m in x["moves"]:
                print("   ", m["dir"], m["verdict"], m["year"], m["place"], repr(m["text"]))
            for m in x["remarks"]:
                print("   ", m["column"], f"[{m['flag']}]" if m["flag"] else "", repr(m["text"]), repr(m["alt"]))
    else:
        write(out)
    return out


def write(out):
    good = [x for x in out if x["score"] >= 0.9]
    d = MAIN / "data/cache/rows"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "rows.tsv", "w", encoding="utf-8") as o:
        o.write("mh_id\tname\tvolume\tpage\timage\tscore\tname_read\theaders\tin\tout\tremarks\n")
        for x in out:
            mv = {m["dir"]: f"{m['verdict']}: {m['text']}" for m in x["moves"]}
            rm = " | ".join(f"{r['column']}{'!' if r['flag'] else ''}: {r['text']}" for r in x["remarks"])
            o.write("\t".join(str(v).replace("\t", " ") for v in (
                x["mh_id"], x["name"], x["volume"], x["page"], x["image"], x["score"], x["name_read"],
                x["headers"], mv["in"], mv["out"], rm)) + "\n")
    with open(MAIN / "data/output/moves_read.tsv", "w", encoding="utf-8") as o:
        o.write("mh_id\tdir\tyear\tplace\ttext\tvolume\tpage\tverdict\n")
        for x in good:
            for m in x["moves"]:
                if m["verdict"] in ("known", "new", "abroad", "within the book"):
                    o.write("\t".join(str(v).replace("\t", " ") for v in (
                        x["mh_id"], m["dir"], m["year"], m["place"], m["text"], x["volume"], x["page"], m["verdict"])) + "\n")
    with open(MAIN / "data/output/remarks_read.tsv", "w", encoding="utf-8") as o:
        o.write("mh_id\tcolumn\tflag\ttext\talt\tvolume\tpage\timage\n")
        for x in good:
            for m in x["remarks"]:
                o.write("\t".join(str(v).replace("\t", " ") for v in (
                    x["mh_id"], m["column"], m["flag"], m["text"], m["alt"], x["volume"], x["page"], x["image"])) + "\n")
    print(len(out), "citations on pages with line files;", len(good), "with the row found (score >= 0.9)")
    print("moves:", dict(Counter(m["verdict"] for x in good for m in x["moves"])))
    print("remarks:", dict(Counter(m["column"] for x in good for m in x["remarks"])))
    print("\nflagged words, row found:")
    for x in good:
        for m in x["remarks"]:
            if m["flag"]:
                print(f"  {x['mh_id']:10} {x['name'][:26]:26} {x['volume'][:24]:24} p.{x['page']:>4} "
                      f"{m['column']:11} [{m['flag']}] {m['text'][:50]}")


if __name__ == "__main__":
    a = sys.argv[1:]
    only = a[a.index("--person") + 1] if "--person" in a else None
    pos = [x for x in a if not x.startswith("--") and x != only]
    main(Path(pos[0]) if pos else MAIN / "data/archive", only)
