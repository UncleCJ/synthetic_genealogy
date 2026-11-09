"""
A person's life as a path of located, dated points, for a map.

Points come from two layers:

    documented  the tree's own events (birth, baptism, residence, marriage,
                emigration, death, burial, ...). `dated` marks those with a
                day and month, or vital events: the history collated by
                hand. Year-only residences are mostly MyHeritage's own
                (one per volume) and are shown, but do not draw the path.
    record      household-examination stays (residences.py): where the
                volumes place the person, by volume years

Each point carries coordinates at the best level available (geocode.py):
the gazetteer place (farm, village, or the place it lies within), else the
parish, else the town or region from OpenStreetMap. The level travels with
the point, so a map can draw its uncertainty.

Points are ordered by their first year (birth and baptism first within a
year, death and burial last). Events without a year are left out of the
path but listed.

Sketch status: one tree. Undated events and places that resolve to no
coordinates are reported, not guessed.
"""
import re
from collections import defaultdict

import geocode

YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
ORDER = {"birth": 0, "baptism": 1, "residence": 5, "marriage": 4, "emigration": 6,
         "immigration": 7, "occupation": 5, "death": 8, "burial": 9}
SKIP = {"person", "family", "_UPD", "Record", "Smart Matching"}


def _span(date):
    ys = [int(y) for y in YEAR.findall(date or "")]
    if not ys:
        return None, None
    d = (date or "").upper()
    if d.startswith(("TO", "BEF")):
        return None, max(ys)
    return min(ys), max(ys)


def where(r, gaz, parish_pts, private, network):
    """(lat, lon, level, source, name) for a row's place, best level first."""
    pid = r.get("place_id")
    if pid and gaz.places.get(pid, {}).get("lat"):
        p = gaz.places[pid]
        return p["lat"], p["lon"], p.get("geo_level", "farm"), p.get("geo_source", ""), gaz.label(pid)
    par = r.get("parish")
    # "Torpet Ödelyckan, Adelöf, Adelöv": try every part before the parish,
    # most specific first, and neighbouring parts joined ("Finnanäs Norrgård")
    parts = [x.strip() for x in (r.get("event_place") or "").split(",") if x.strip()]
    if par and parts:
        k = next((i for i, x in enumerate(parts) if gaz.parish(x) == par), len(parts))
        before = parts[:k]
        tries = before + [f"{a} {b}" for a, b in zip(before, before[1:])]
        for t in tries:
            q = gaz.place(par, t)
            if q and gaz.places[q].get("lat"):
                g = gaz.places[q]
                return g["lat"], g["lon"], g.get("geo_level", "farm"), g.get("geo_source", ""), gaz.label(q)
    if par in parish_pts:
        lat, lon = parish_pts[par]
        name = (r.get("farm") or r.get("place") or "")
        return lat, lon, "parish", "wikidata", f"{name + ', ' if name else ''}{par}"
    if r.get("event_place"):
        geocode.OFFLINE[0] = not network
        try:
            hit = geocode.locality(private, r["event_place"])
        except RuntimeError:
            hit = None
        if hit:
            return hit[0], hit[1], hit[2], hit[3], hit[4]
    return None


def build(rows, people, gaz, private, network=True):
    """person xref -> list of points; also unplaced events per person."""
    parish_pts = {n: (p["lat"], p["lon"]) for n, p in gaz.parishes.items() if p.get("lat")}
    paths, unplaced = defaultdict(list), defaultdict(list)
    seen = set()
    for r in rows:
        ev = r.get("event") or ""
        if ev in SKIP or not r.get("event_place"):
            continue
        key = (r["person"], ev, r.get("event_date"), r.get("event_place"))
        if key in seen:
            continue
        seen.add(key)
        y0, y1 = _span(r.get("event_date"))
        loc = where(r, gaz, parish_pts, private, network)
        if not loc or (y0 is None and y1 is None):
            unplaced[r["person"]].append(dict(event=ev, date=r.get("event_date", ""),
                                              place=r.get("event_place", ""),
                                              why="no year" if loc else "no coordinates"))
            continue
        dated = bool(re.search(r"\b\d{1,2}\s+[A-Z]{3}\b", (r.get("event_date") or "").upper())) \
            or ev in ("birth", "baptism", "marriage", "death", "burial")
        paths[r["person"]].append(dict(kind="documented", event=ev, date=r.get("event_date", ""),
                                       dated=dated, parish=r.get("parish", ""),
                                       y0=y0 if y0 is not None else y1, y1=y1,
                                       name=loc[4], lat=loc[0], lon=loc[1], level=loc[2],
                                       source=loc[3], text=r.get("event_place", "")))
    for pid, P in people.items():
        for s in P.get("record", []):
            r = dict(parish=s["parish"], place_id=None, farm=s["place"])
            pidx = gaz.place(s["parish"], s["place"]) if s["place"] else None
            r["place_id"] = pidx
            loc = where(r, gaz, parish_pts, private, network=False)
            if not loc:
                continue
            paths[pid].append(dict(kind="record", event="household examination",
                                   date=f"{s['start']}–{s['end']}", y0=s["start"], y1=s["end"],
                                   name=loc[4], lat=loc[0], lon=loc[1], level=loc[2], source=loc[3],
                                   text="; ".join(f"{v} p. {p}" for v, p, _, _ in s["volumes"])))
    for pid in paths:
        paths[pid] = _aggregate_residences(paths[pid])
        paths[pid].sort(key=lambda p: (p["y0"], ORDER.get(p["event"], 5), p["kind"] != "documented"))
    return dict(paths), dict(unplaced)


def _aggregate_residences(pts):
    """Repeated residence entries at one place and period -> one point
    (stays.py); the point says how many entries it stands for."""
    import stays
    res = [p for p in pts if p["kind"] == "documented" and p["event"] == "residence"]
    rest = [p for p in pts if not (p["kind"] == "documented" and p["event"] == "residence")]
    agg = stays.aggregate(res, key=lambda p: (p["name"], round(p["lat"], 4), round(p["lon"], 4)))
    info = {st["key"]: st["items"][0] for st in agg}
    # general = a rote, or only the parish known (a farm placed at its
    # parish's point is named "Farm, Parish" and still counts as a farm)
    general = lambda k: info[k]["name"].lower().endswith(" rote") \
        or (info[k]["level"] == "parish" and "," not in info[k]["name"])
    for st in stays.drop_general(agg, lambda k: info[k].get("parish"), general):
        p = dict(st["items"][0])
        p.update(y0=st["y0"], y1=st["y1"], date=st["label"], n=st["n"], group=st["group"],
                 dated=st["dated"] or p.get("dated", False),
                 also=[a["items"][0]["name"] for a in st.get("also", [])])
        rest.append(p)
    return rest


def spouses(tree):
    out = defaultdict(set)
    for f in tree.families.values():
        if f["husb"] and f["wife"]:
            out[f["husb"]].add(f["wife"])
            out[f["wife"]].add(f["husb"])
    return out
