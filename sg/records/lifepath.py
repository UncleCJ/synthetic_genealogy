"""
A person's life path, its steps and its loose end (roadmap, "Focus
selection"), from the located points the geography view collects (tree
events, stays, record citations).

The life path, as settled here (2026-11-23): every point of the person
with a year, ordered by its first year, ties by the kind of event (birth
first, burial last), then by its last year. Undated points are left out. A
**step** is a point at a different place from where the person was last
placed; a point placed on its parish, after one on a farm in that parish,
is the same place written less precisely, not a move. Its distance is
great-circle between the two points, approximate when either sits on a
parish, town or wider point. A **loose end** is where a path stops with no
death or burial recorded, for someone born more than 120 years ago (or,
with no birth year, last seen more than 100 years ago): the last point,
the year, the age, and the household volumes of that parish that would
continue it (from Riksarkivet's inventory, offline cache only), led by one
the person or their household is already cited in (lead).

Unvalidated sketch: a residence written with a year range orders by its
first year; a household citation spans its volume's years, so a move
inside one volume's span may come out in either order.
"""
import math
import re
from datetime import date

ORDER = {"birth": 0, "baptism": 1, "birth record": 1, "confirmation": 2, "marriage": 4,
         "marriage record": 4, "emigration": 7, "moving out": 7, "death": 8, "death record": 8,
         "burial": 9}
DEATH = {"death", "burial", "death record"}
LEAVING = {"emigration": "emigrated", "moving out": "moved out"}
COARSE = {"parish", "town", "region", "country"}
HOUSEHOLD = re.compile(r"/A I(?: |/|$)|/A II a(?:/|$)")


def year(pt):
    return pt.get("y0") if pt.get("y0") is not None else pt.get("y1")


def path(points):
    """A person's dated points in life order."""
    pts = [p for p in points if year(p) is not None]
    return sorted(pts, key=lambda p: (year(p), ORDER.get(p["t"], 5), p.get("y1") or year(p)))


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def same_place(a, b):
    """The same place, or one written less precisely than the other."""
    if (a["lat"], a["lon"]) == (b["lat"], b["lon"]):
        return True
    ka, kb = a.get("place") or "", b.get("place") or ""
    if ka and ka == kb:
        return True
    for x, y in ((a, b), (b, a)):
        if (x.get("lv") == "parish" or (x.get("place") or "").startswith("parish:")) and \
                x.get("parish") and x.get("parish") == y.get("parish"):
            return True
    return bool(ka and kb) and (ka.startswith(kb + "/") or kb.startswith(ka + "/"))


def steps(pts):
    """Steps along a path: (from point, to point, km, approximate). Each
    point is compared with where the person was last placed: a coarser point
    that agrees with it (the parish of the farm) keeps the farm, so a move
    between two farms is still seen across a parish-level event."""
    out = []
    cur = pts[0] if pts else None
    for b in pts[1:]:
        if same_place(cur, b):
            if cur.get("lv") in COARSE and b.get("lv") not in COARSE:
                cur = b
            continue
        out.append((cur, b, round(km(cur, b), 1), cur.get("lv") in COARSE or b.get("lv") in COARSE))
        cur = b
    return out


def loose_end(pts, born=None, died=None, today=None):
    """The last point of a path with no death recorded, for someone presumed
    dead; else None."""
    if not pts or died is not None or any(p["t"] in DEATH for p in pts):
        return None
    now = (today or date.today()).year
    last = pts[-1]
    seen = last.get("y1") or year(last)
    if (born is not None and born > now - 120) or (born is None and seen > now - 100):
        return None
    return dict(point=last, year=seen, age=seen - born if born is not None else None,
                left=LEAVING.get(last["t"], ""))


def _span(s):
    ys = [int(y) for y in re.findall(r"1[5-9]\d\d", s or "")]
    return (min(ys), max(ys)) if ys else None


def next_volumes(inventory, seen):
    """Household volumes of a parish archive that run on past the year last
    seen, earliest first: (code, years, viewer)."""
    out = []
    for code, v in (inventory or {}).items():
        sp = _span(v.get("years"))
        if sp and HOUSEHOLD.search(code) and sp[1] > seen:
            out.append((sp[0], code, v.get("years", ""), v.get("viewer", "")))
    return [(c, y, w) for _, c, y, w in sorted(out)]


def lead(nxt, cited=None, house=None):
    """How answerable a loose end is, from the later household volumes
    (next_volumes): "cited" when the person is cited in one of them already
    (the path stops only because that citation has no place or years),
    "household" when a parent, spouse, sibling or child is (a page to open),
    else "". Returns (lead, ((code, years, viewer), page, who) or None): the
    earliest volume, the person's own citation first."""
    cited, house = cited or {}, house or {}
    for v in nxt:
        if v[0] in cited:
            return "cited", (v, cited[v[0]], "")
    for v in nxt:
        if v[0] in house:
            who, pg = house[v[0]]
            return "household", (v, pg, who)
    return "", None
