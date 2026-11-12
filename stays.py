"""
Residence entries aggregated into stays: one per person, place and
continuous period, with the original entries kept as its evidence.

MyHeritage adds a residence for every record match, so the same farm and
volume recur. Aggregated into a derived view (MyHeritage and the store are
not changed): entries at one place whose years overlap or touch (gap <= 1
year) become one stay; day-dated entries are never lost (their dates label
the stay); stays at different places sharing exactly one year-only span
form a period group; a stay known only as a rote, parish or town is folded
into an overlapping stay at a specific farm (drop_general, kept as `also`).
"Same place" is the gazetteer place, else the place text as written.
Details and examples: docs/records.md, "Residences and stays". Sketch: no
attempt to order moves inside a volume period.
"""
from collections import defaultdict

from intervals import is_dated, runs, year_count  # is_dated is also used by importers


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
    out = [dict(key=k, y0=a, y1=b, items=[it for _, _, it in run])
           for k, its in by_key.items()
           for a, b, run in runs(its, lambda t: (t[0], t[1]), gap)]
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
        years = g["y1"] - g["y0"] + 1
        covered = year_count(g["y0"], g["y1"], [(s["y0"], s["y1"]) for s in hit])
        if not hit or covered * 2 < years or (years > 1 and covered < 2):
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
