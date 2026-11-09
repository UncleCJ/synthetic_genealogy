"""
Residence entries aggregated into stays: one per person, place and
continuous period, with the original entries kept as its evidence.

MyHeritage adds a residence for every record match: each household-
examination page a person appears on becomes "Residence: <farm>, BET <first
year of the volume> AND <last year>". The same farm and volume recur when
several family members' records were matched, and consecutive volumes at
one farm give consecutive entries. Aggregated (a derived view; MyHeritage
and the tree store are not changed):

1. entries at the same place whose years overlap or touch (gap <= 1 year)
   become one stay spanning them all ("Groröd 1854-1860" + 3 x "Groröd
   1861-1867" -> Groröd 1854-1867, 4 entries);
2. day-dated entries (collated by hand from the records) are never lost:
   the stay keeps their exact dates as its label, and year-only entries at
   the same place in the same years become their evidence;
3. stays at different places that share exactly the same year-only span
   (one volume's period) form a *period group*: the person appears at
   several households in that volume (moved within the period, or served
   in another household). They stay separate places, shown together.

4. farm before district (drop_general): a stay known only as a rote, the
   parish or a town is folded into an overlapping stay at a specific farm
   in the same parish when those cover at least half of its years
   ("Munkebo rote 1870-1882" next to Möjered, Gettered, Långås in those
   years), kept there as `also`.

"Same place" is the gazetteer place when the entry resolved to one, else
the place text as written. Sketch: no attempt to order moves inside a
volume period; the records do not say.
"""
import re
from collections import defaultdict

DAY = re.compile(r"\b\d{1,2}\s+[A-Za-z]{3}\b")


def is_dated(date):
    return bool(DAY.search(date or ""))


def aggregate(items, key, y0="y0", y1="y1", date="date", gap=1):
    """items: dicts with years (y0, y1; either may be None) and a date
    text. key(item) -> place key. Returns stays: dicts with key, y0, y1,
    label, dated, n, items, group (period group id or None)."""
    by_key = defaultdict(list)
    loose = []
    for it in items:
        a = it.get(y0) if it.get(y0) is not None else it.get(y1)
        b = it.get(y1) if it.get(y1) is not None else a
        if a is None:
            loose.append(dict(key=key(it), y0=None, y1=None, items=[it]))
            continue
        by_key[key(it)].append((a, b, it))
    out = []
    for k, its in by_key.items():
        cur = None
        for a, b, it in sorted(its, key=lambda t: (t[0], t[1])):
            if cur and a <= cur["y1"] + gap:
                cur["y1"] = max(cur["y1"], b)
                cur["items"].append(it)
            else:
                cur = dict(key=k, y0=a, y1=b, items=[it])
                out.append(cur)
    out += loose
    for st in out:
        dated = [it[date] for it in st["items"] if is_dated(it.get(date))]
        st["dated"] = bool(dated)
        st["n"] = len(st["items"])
        if dated:
            st["label"] = "; ".join(dict.fromkeys(dated))
        elif st["y0"] is not None:
            st["label"] = f"{st['y0']}–{st['y1']}" if st["y1"] != st["y0"] else str(st["y0"])
        else:
            st["label"] = next((it.get(date) for it in st["items"] if it.get(date)), "")
        st["group"] = None
    # period groups: same year-only span, different places
    spans = defaultdict(list)
    for st in out:
        if not st["dated"] and st["y0"] is not None and st["y1"] != st["y0"]:
            spans[(st["y0"], st["y1"])].append(st)
    for (a, b), sts in spans.items():
        if len({s["key"] for s in sts}) > 1:
            for s in sts:
                s["group"] = f"{a}–{b}"
    out.sort(key=lambda s: (s["y0"] if s["y0"] is not None else 9999, str(s["key"])))
    return out


def drop_general(stays, parish_of, is_general):
    """Farm before district: a stay known only at a general level (a rote,
    the parish, a town) is dropped when the same person has a stay at a
    specific place in the same parish whose years overlap; it is kept on
    that stay as `also` (its label), so nothing is lost. parish_of(key)
    and is_general(key) describe a stay's place."""
    specific = [s for s in stays if not is_general(s["key"])]
    out = []
    for g in stays:
        if not is_general(g["key"]) or g["y0"] is None:
            out.append(g)
            continue
        hit = [s for s in specific if s["y0"] is not None and parish_of(s["key"]) == parish_of(g["key"])
               and s["y0"] <= g["y1"] and g["y0"] <= s["y1"]]
        # the specific stays must cover at least half of the general stay's
        # years: touching in one boundary year is not the same residence
        years = set(range(g["y0"], g["y1"] + 1))
        covered = set().union(*[set(range(max(s["y0"], g["y0"]), min(s["y1"], g["y1"]) + 1)) for s in hit]) \
            if hit else set()
        if not hit or len(covered) * 2 < len(years) or (len(years) > 1 and len(covered) < 2):
            out.append(g)
            continue
        for s in hit:
            s.setdefault("also", []).append(g)
    # a period group that lost members to this may now be a single place
    groups = {}
    for s in out:
        if s.get("group"):
            groups.setdefault(s["group"], set()).add(str(s["key"]))
    for s in out:
        if s.get("group") and len(groups[s["group"]]) < 2:
            s["group"] = None
    return out
