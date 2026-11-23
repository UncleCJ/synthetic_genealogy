"""
A person's life path, its steps (labelled by where the family was: see
the section at the end) and its loose end (roadmap, "Focus selection"), from the located points the geography view collects (tree
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


# ---- steps in the light of the family (roadmap: context of a life)
#
# A step labelled by where the person's relatives were: back to a place
# they lived before, to the parents (to an ageing or widowed parent), to a
# relative's farm or near one (same parish), together with a relative
# taking the same step, following one who went there before. Relatives
# come from the tree's families only (names are not identities); where
# someone was is read off their own path, each place held from its point
# until the next step. Household citations span a volume's years, so
# "the same time" means overlapping spans, not dates.

ROLES = {  # relation -> (man, woman, either)
    "parent": ("father", "mother", "parent"), "child": ("son", "daughter", "child"),
    "sibling": ("brother", "sister", "sibling"), "spouse": ("husband", "wife", "spouse"),
    "grandparent": ("grandfather", "grandmother", "grandparent"),
    "grandchild": ("grandson", "granddaughter", "grandchild"),
    "uncle": ("uncle", "aunt", "uncle or aunt"), "nibling": ("nephew", "niece", "nephew or niece"),
    "cousin": ("cousin", "cousin", "cousin"),
    "parent-in-law": ("father-in-law", "mother-in-law", "parent-in-law"),
    "child-in-law": ("son-in-law", "daughter-in-law", "child-in-law"),
    "sibling-in-law": ("brother-in-law", "sister-in-law", "sibling-in-law"),
}
CLOSE = list(ROLES)   # nearest first, for the order of labels


def kin_roles(families, children):
    """{person: {relative: relation}} from {family: (husband, wife)} and
    {family: [children]}: parents, children, siblings (half included),
    spouses, grandparents and grandchildren, uncles and aunts, nephews and
    nieces, cousins, in-laws. The nearest relation wins."""
    par, kids, sp = {}, {}, {}
    for f, (h, w) in families.items():
        for c in children.get(f, ()):
            par.setdefault(c, set()).update(x for x in (h, w) if x)
            for x in (h, w):
                if x:
                    kids.setdefault(x, set()).add(c)
        if h and w:
            sp.setdefault(h, set()).add(w)
            sp.setdefault(w, set()).add(h)
    P = lambda x: par.get(x, set())
    K = lambda x: kids.get(x, set())
    S = lambda x: sp.get(x, set())
    sib = lambda x: {s for p in P(x) for s in K(p)} - {x}
    out = {}
    for x in set(par) | set(kids) | set(sp):
        r = {}
        rel = [("parent", P(x)), ("child", K(x)), ("sibling", sib(x)), ("spouse", S(x)),
               ("grandparent", {g for p in P(x) for g in P(p)}),
               ("grandchild", {g for c in K(x) for g in K(c)}),
               ("uncle", {u for p in P(x) for u in sib(p)}),
               ("nibling", {n for s in sib(x) for n in K(s)}),
               ("cousin", {c for p in P(x) for u in sib(p) for c in K(u)}),
               ("parent-in-law", {q for s in S(x) for q in P(s)}),
               ("child-in-law", {q for c in K(x) for q in S(c)}),
               ("sibling-in-law", {q for s in S(x) for q in sib(s)} | {q for s in sib(x) for q in S(s)})]
        for k, ys in rel:
            for y in ys:
                if y != x:
                    r.setdefault(y, k)
        out[x] = r
    return out


def stays_of(path, died=None):
    """[(point, from year, to year)]: each place the path holds, from its
    point to the next step (or the point's own last year, or death)."""
    if not path:
        return []
    pos = [path[0]] + [b for _, b, *_ in steps(path)]
    out = []
    for i, p in enumerate(pos):
        y0 = year(p)
        nxt = year(pos[i + 1]) if i + 1 < len(pos) else None
        y1 = nxt if nxt is not None else max(p.get("y1") or y0, died or 0, y0)
        later = [q.get("y1") or year(q) for q in path if year(q) is not None and year(q) >= y0 and same_place(q, p)]
        out.append((p, y0, max([y1] + ([min(max(later), nxt)] if nxt is not None and later else []))))
    return out


def _exact(a, b):
    return same_place(a, b) and a.get("lv") not in COARSE and b.get("lv") not in COARSE


def labels(pid, paths, roles, life):
    """[(from point, to point, km, approximate, [label])] for one person's
    steps. A label is (kind, relative or "", year or None): back (to a place
    lived in before, the year first there), born (back to the birthplace),
    parents (a parent there then), ageing (back to a parent aged 60 or
    more, or widowed, the person grown up), kin (a relative on that farm),
    near (a relative in that parish, none on the farm), together (a relative
    taking the same step within a year), following (a relative who went
    there before and was still there, the year they came). life: {person:
    (born, died)}."""
    path = paths.get(pid) or []
    born, _ = life.get(pid, (None, None))
    rel = roles.get(pid, {})
    stays = {r: stays_of(paths.get(r) or [], life.get(r, (None, None))[1]) for r in rel if paths.get(r)}
    rsteps = {r: steps(paths[r]) for r in stays}
    order = lambda r: CLOSE.index(rel[r])
    out = []
    seen = [path[0]] if path else []
    for a, b, km_, approx in steps(path):
        y = year(b)
        lab = []
        before = [p for p in seen[:-1] if same_place(p, b)]
        if before:
            lab.append(("born" if before[0] is path[0] and path[0]["t"] in ("birth", "baptism") else "back", "",
                        year(before[0])))
        at = {}
        for r in sorted(stays, key=order):
            for p, y0, y1 in stays[r]:
                if y0 is not None and y0 <= y + 1 and y1 >= y - 1:
                    if _exact(p, b):
                        at[r] = "kin"
                    elif r not in at and p.get("parish") and p.get("parish") == b.get("parish"):
                        at[r] = "near"
        pars = [r for r, k in at.items() if k == "kin" and rel[r] == "parent"]
        for r in pars:
            pb, pd = life.get(r, (None, None))
            other = [q for q, k in rel.items() if k == "parent" and q != r]
            widowed = any(life.get(q, (None, None))[1] and life[q][1] <= y for q in other)
            old = (pb is not None and y - pb >= 60) or widowed
            grown = born is not None and y - born >= 20
            lab.append(("ageing" if old and grown else "parents", r, None))
        for r in sorted(at, key=order):
            if r in pars:
                continue
            together = any(abs((year(b2) or 0) - y) <= 1 and same_place(b2, b) and same_place(a2, a)
                           for a2, b2, *_ in rsteps[r])
            if together:
                lab.append(("together", r, None))
                continue
            came = [year(b2) for a2, b2, *_ in rsteps[r] if _exact(b2, b) and year(b2) is not None and y - 10 <= year(b2) < y]
            if came:
                lab.append(("following", r, max(came)))
            lab.append((at[r], r, None))
        if any(k in ("kin", "parents", "ageing", "together") for k, *_ in lab):
            lab = [x for x in lab if x[0] != "near"]      # on the farm says more than in the parish
        else:
            lab = [x for x in lab if x[0] != "near"] + [x for x in lab if x[0] == "near"][:2]
        out.append((a, b, km_, approx, lab[:6]))
        seen.append(b)
    return out
