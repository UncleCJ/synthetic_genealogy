"""Are they there? Scan a few images of a volume for a name (and birth year).
python3 find.py C0012345 201 205 "Anna Maria" 1867
Pages are cached in ./pages (run it from a folder under data/: private)."""
import difflib
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch import get

HERE = Path(__file__).parent


def norm(s):
    s = s.lower()
    for a, b in (("ph", "f"), ("w", "v"), ("ſ", "s"), ("é", "e"), ("á", "a")):
        s = s.replace(a, b)
    return re.sub(r"[^a-zåäö ]", "", s)


def vision(path):
    out = subprocess.run([str(HERE / "vision"), str(path)], capture_output=True, text=True).stdout
    for line in out.splitlines():
        box, cands = line.split("\t")
        x, y, w, h = map(float, box.split())
        yield x, y, w, h, [c.rsplit("|", 1)[0] for c in cands.split("  ")]


SQUINT = str.maketrans("oOQDGbSsZzBlIi|!qgAT", "00006655228111119947")


def year_ok(year, text):
    """Leading token of the year cell, look-alike letters as digits; the
    last two digits within one digit of the expected year."""
    tok = (text.split() or [""])[0].translate(SQUINT)
    d = re.sub(r"\D", "", tok)
    if len(d) < 2:
        return False
    d = d[:2] if len(d) in (2, 3) else d[2:4]
    return sum(a != b for a, b in zip(d, year[-2:])) <= 1


def score(target, text):
    """Best fuzzy ratio of the target's words against the text's words."""
    tw, xw = norm(target).split(), norm(text).split()
    if not xw:
        return 0.0
    return sum(max(difflib.SequenceMatcher(None, t, x).ratio() for x in xw) for t in tw) / len(tw)


if __name__ == "__main__":
    series, a, b, name = sys.argv[1:5]
    year = sys.argv[5] if len(sys.argv) > 5 else None
    od = Path.cwd() / "pages"; od.mkdir(exist_ok=True)
    for n in range(int(a), int(b) + 1):
        p, _ = get(series, n, "full", "4000,", od)
        lines = list(vision(p))
        page = next((c[0] for x, y, w, h, c in lines if y < 0.12 and x < 0.3 and re.fullmatch(r"\d{1,3}", c[0])), "?")
        farm = next((c[0] for x, y, w, h, c in lines if y < 0.12 and 0.2 < x < 0.5 and not c[0].isdigit()), "?")
        hits = []
        for x, y, w, h, c in lines:
            if x > 0.24 or y < 0.18:
                continue  # left page body only (names)
            s = max(score(name, t) for t in c)
            if s >= 0.6:
                # year: text on the same line in the year column (x 0.49-0.55 of the spread)
                yrs = [cc[0] for xx, yy, ww, hh, cc in lines if 0.24 < xx < 0.29 and abs(yy - y) < 0.012]
                ok = year and any(year_ok(year, v) for v in yrs)
                hits.append((s, c[0], yrs, ok, y))
        print(f"image {n} page {page} farm {farm!r}")
        for s, t, yrs, ok, y in sorted(hits, reverse=True):
            print(f"   {s:.2f} {t!r} years={yrs} {'YEAR MATCH' if ok else ''} (y={y:.3f})")
