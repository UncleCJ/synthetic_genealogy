"""
Residence histories from household-examination citations, set against the
residence events collated by hand in the tree.

MyHeritage records a person's presence per volume ("Källeryd A II a/2,
1906-1921, Hagelstorp, p. 35"), not when they moved. This module:

1. turns each person's volume citations into *record stays*: one per
   volume and place, merged across consecutive volumes at the same place
   (gazetteer place, else the farm name as written);
2. reads the tree's own RESI events (BET ... AND ..., FROM ... TO ...),
   the history already collated by hand, as *documented stays*, with
   MyHeritage's repeated entries aggregated (stays.py: same place and
   continuous years -> one stay; n = entries behind it);
3. reports, per person:
   - gaps: years between record stays (within the lifetime) with no
     volume cited, and the volumes to open next (the following volume of
     the earlier stay's series, the preceding one of the later stay's),
     looked up at Riksarkivet so the years and a viewer link are known;
   - moves between parishes, bracketed by the first volume year in the
     new parish and the last in the old (volumes cover years, not dates),
     with any documented residence date that falls inside;
   - not yet collated: record stays that no documented stay covers.

Inaccuracy accepted: a stay's years are the volume's years, so moves are
only bracketed. Sketch: one tree; volumes with lettered numbers ("4c")
get no next-volume suggestion.

    python residences.py               # data/residences.csv + summary
    python residences.py MH:I1         # one person's timeline as text
"""
import csv
import re
import sys
from collections import defaultdict

import riksarkivet

YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
RECORD_TIERS = ("mh-record", "ra-full", "ra-link")
# Only household examinations and parish books say where someone lived;
# birth (C), marriage (E) and death (F) books and moving lists (B) are events.
RESIDENCE_SERIES = {"A I", "A II", "A II a", "A II b"}


def _years(text):
    ys = [int(y) for y in YEAR.findall(text or "")]
    return (min(ys), max(ys)) if ys else (None, None)


def _resi_span(date):
    """GEDCOM residence date -> (start, end); open ends None."""
    d = (date or "").upper()
    a, b = _years(d)
    if a is None:
        return None, None
    if d.startswith("TO") or d.startswith("BEF"):
        return None, b
    if d.startswith("FROM") and " TO " not in d or d.startswith("AFT"):
        return a, None
    return a, b


def _place_key(r):
    return (r.get("parish") or "", r.get("village") or r.get("place") or (r.get("farm") or "").strip())


def _shown(r):
    """A residence's own place, with the village or rote it lies in:
    "Gettered (Kollerö rote)"."""
    own = r.get("place") or (r.get("farm") or "").strip()
    village = r.get("village") or ""
    return f"{own} ({village})" if own and village and village != own else (own or village)


def stays(rows):
    """person -> dict(record=[...], documented=[...], vital=[...], label, kin, mh_id)."""
    people = defaultdict(lambda: dict(record=[], documented=[], vital=[]))
    for r in rows:
        P = people[r["person"]]
        P.update(label=r.get("label", ""), kin=r.get("kin", ""), mh_id=r.get("mh_id", ""),
                 lineage=r.get("lineage", ""), branch=r.get("branch", ""))
        if r.get("tier") in RECORD_TIERS and r.get("volume") \
                and r.get("series") in RESIDENCE_SERIES:
            y1, y2 = _years(r.get("ra_years") or r.get("years"))
            if y1 is None:
                continue
            P["record"].append(dict(start=y1, end=y2, parish=r.get("parish", ""),
                                    place=_place_key(r)[1], farm=r.get("farm", ""),
                                    volume=r["volume"], page=r.get("page", ""),
                                    code=r.get("ra_code", ""), viewer=r.get("ra_viewer", ""),
                                    series=r.get("series", ""), vol=r.get("vol", "")))
        elif r.get("tier") == "plac-only" and r.get("event") == "residence":
            a, b = _resi_span(r.get("event_date"))
            if a or b:
                P["documented"].append(dict(start=a, end=b, parish=r.get("parish", ""),
                                            place=_shown(r), date=r.get("event_date", ""),
                                            text=r.get("event_place", ""),
                                            pid=r.get("place_id") or ""))
        elif r.get("tier") == "plac-only" and r.get("event") in ("birth", "death", "baptism", "burial"):
            y, _ = _years(r.get("event_date"))
            if y:
                P["vital"].append(dict(event=r["event"], year=y, parish=r.get("parish", "")))
    for P in people.values():
        P["record"] = _merge(P["record"])
        P["documented"] = _aggregate_documented(P["documented"])
    return people


def _general_key(pid, name=""):
    """A rote, a bare parish, or a place outside the gazetteer (town)."""
    pid = str(pid or "")
    return (not pid or pid.startswith(("parish:", "osm:", "(")) or pid.lower().endswith(" rote")
            or str(name).lower().endswith(" rote"))


def _aggregate_documented(docs):
    """MyHeritage's repeated residence entries as stays (stays.py): one per
    place and continuous period, n = entries behind it."""
    import stays
    out = []
    agg = stays.aggregate(docs, key=lambda d: d["pid"] or (d["parish"], d["place"]), y0="start", y1="end")
    parish = {st["key"]: st["items"][0]["parish"] for st in agg}
    general = {st["key"]: _general_key(st["key"] if isinstance(st["key"], str) else "",
                                       st["items"][0]["place"]) for st in agg}
    for st in stays.drop_general(agg, parish.get, general.get):
        first = st["items"][0]
        out.append(dict(start=st["y0"] if any(i["start"] is not None for i in st["items"]) else None,
                        end=st["y1"] if any(i["end"] is not None for i in st["items"]) else None,
                        parish=first["parish"], place=first["place"], date=st["label"],
                        text=first["text"], n=st["n"], group=st["group"], dated=st["dated"],
                        also=[a["items"][0]["place"] or a["items"][0]["parish"] for a in st.get("also", [])]))
    return out


def _merge(recs):
    """One stay per run of volumes at the same parish and place."""
    seen, uniq = set(), []
    for s in sorted(recs, key=lambda s: (s["start"], s["end"], s["volume"], s["page"])):
        k = (s["volume"], s["page"], s["place"])
        if k not in seen:
            seen.add(k)
            uniq.append(dict(s, volumes=[(s["volume"], s["page"], s["code"], s["viewer"])]))
    out = []
    for s in uniq:
        last = next((o for o in reversed(out)
                     if (o["parish"], o["place"]) == (s["parish"], s["place"])), None)
        if last and s["start"] <= last["end"] + 1 and last is out[-1]:
            last["end"] = max(last["end"], s["end"])
            last["volumes"] += s["volumes"]
            last.update(series=s["series"], vol=s["vol"], code=s["code"])
        else:
            out.append(s)
    return out


def _neighbour(ra, code, step):
    """The volume after (step=+1) or before (-1) `code` in its series; at
    the end of series A I, the first of A II a. None if unknown."""
    m = re.match(r"^(.*)/([^/]+)/(\d+)$", code or "")
    if not m or ra is None:
        return None
    archive, series, n = m[1], m[2], int(m[3])
    cands = [f"{archive}/{series}/{n + step}"] if n + step > 0 else []
    if step > 0 and series == "A I":
        cands.append(f"{archive}/A II a/1")
    for c in cands:
        try:
            v = ra.volume(c)
        except RuntimeError:
            continue
        if v:
            return v
    return None


def analyse(P, ra=None):
    """Gaps (with volumes to open), moves and not-yet-collated stays."""
    rec = P["record"]
    born = next((v["year"] for v in P["vital"] if v["event"] in ("birth", "baptism")), None)
    died = next((v["year"] for v in P["vital"] if v["event"] in ("death", "burial")), None)
    gaps, moves, uncollated = [], [], []
    by_time = sorted(rec, key=lambda s: (s["start"], s["end"]))
    covered_to = None
    for i, s in enumerate(by_time):
        if covered_to is not None and s["start"] > covered_to + 1:
            prev = max((x for x in by_time[:i]), key=lambda x: x["end"])
            look = [v for v in (_neighbour(ra, prev.get("code"), +1),
                                _neighbour(ra, s.get("code"), -1)) if v]
            gaps.append(dict(start=covered_to + 1, end=s["start"] - 1,
                             after=f"{prev['parish']} {prev['place']}".strip(),
                             before=f"{s['parish']} {s['place']}".strip(),
                             look=[dict(code=v["code"], years=v["years"], viewer=v["viewer"])
                                   for v in look]))
        covered_to = max(covered_to or s["end"], s["end"])
    if by_time and died and covered_to and died > covered_to + 1:
        last = max(by_time, key=lambda x: x["end"])
        v = _neighbour(ra, last.get("code"), +1)
        gaps.append(dict(start=covered_to + 1, end=died, after=f"{last['parish']} {last['place']}",
                         before=f"death {died}", look=[dict(code=v["code"], years=v["years"],
                                                            viewer=v["viewer"])] if v else []))
    # Moves between parishes: one span per parish (first to last volume
    # year), in order of start; the move lies between the next parish's
    # first year and the previous parish's last (they often overlap: the
    # old volume still lists the household, the new one already does).
    spans = {}
    for s in by_time:
        a0, a1 = spans.get(s["parish"], (s["start"], s["end"]))
        spans[s["parish"]] = (min(a0, s["start"]), max(a1, s["end"]))
    order = sorted(spans.items(), key=lambda kv: kv[1])
    for (pa, (a0, a1)), (pb, (b0, b1)) in zip(order, order[1:]):
        lo, hi = sorted((b0, a1))
        hint = [d["date"] for d in P["documented"] if d["parish"] == pb and d["start"]
                and lo - 1 <= d["start"] <= hi + 1]
        moves.append(dict(frm=pa, to=pb, between=(lo, hi), documented=hint))
    for s in rec:
        if not any(_covers(d, s) for d in P["documented"]):
            uncollated.append(s)
    return dict(born=born, died=died, gaps=gaps, moves=moves, uncollated=uncollated)


def _covers(d, s):
    """A documented stay covers a record stay if parish matches (or is
    unknown) and their years overlap."""
    if d["parish"] and s["parish"] and d["parish"] != s["parish"]:
        return False
    a = d["start"] if d["start"] is not None else -9999
    b = d["end"] if d["end"] is not None else 9999
    return a <= s["end"] and s["start"] <= b


def run(rows, ra=None, people_filter=None):
    out = {}
    for pid, P in stays(rows).items():
        if not P["record"] or (people_filter and P.get("mh_id") not in people_filter):
            continue
        out[pid] = dict(P, **analyse(P, ra))
    return out


def write_csv(res, path):
    cols = ["mh_id", "label", "kin", "kind", "start", "end", "parish", "place", "detail"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        for P in res.values():
            base = dict(mh_id=P["mh_id"], label=P["label"], kin=P["kin"])
            for s in P["record"]:
                w.writerow(dict(base, kind="record", start=s["start"], end=s["end"],
                                parish=s["parish"], place=s["place"],
                                detail="; ".join(f"{v} p. {p}" for v, p, _, _ in s["volumes"])))
            for d in P["documented"]:
                w.writerow(dict(base, kind="documented", start=d["start"], end=d["end"],
                                parish=d["parish"], place=d["place"], detail=d["date"]))
            for g in P["gaps"]:
                w.writerow(dict(base, kind="gap", start=g["start"], end=g["end"],
                                parish="", place=f"{g['after']} → {g['before']}",
                                detail="; ".join(f"{l['code']} ({l['years']})" for l in g["look"])))
            for m in P["moves"]:
                w.writerow(dict(base, kind="move", start=m["between"][0], end=m["between"][1],
                                parish="", place=f"{m['frm']} → {m['to']}", detail="; ".join(m["documented"])))
            for s in P["uncollated"]:
                w.writerow(dict(base, kind="not collated", start=s["start"], end=s["end"],
                                parish=s["parish"], place=s["place"],
                                detail="; ".join(f"{v} p. {p}" for v, p, _, _ in s["volumes"])))


def _print(P):
    print(f"{P['label']}  born {P['born']}  died {P['died']}")
    for s in P["record"]:
        print(f"  record     {s['start']}–{s['end']}  {s['parish']:12} {s['place']:24} "
              + ", ".join(f"{v} p.{p}" for v, p, _, _ in s["volumes"]))
    for d in sorted(P["documented"], key=lambda d: d["start"] or d["end"] or 0):
        print(f"  documented {d['start'] or ''}–{d['end'] or ''}  {d['parish']:12} {d['place']:24} {d['date']}")
    for g in P["gaps"]:
        print(f"  GAP        {g['start']}–{g['end']}  {g['after']} → {g['before']}; open: "
              + (", ".join(f"{l['code']} ({l['years']})" for l in g["look"]) or "?"))
    for m in P["moves"]:
        print(f"  MOVE       {m['between'][0]}–{m['between'][1]}  {m['frm']} → {m['to']}"
              + (f"  (documented: {', '.join(m['documented'])})" if m["documented"] else ""))
    for s in P["uncollated"]:
        print(f"  not collated: {s['start']}–{s['end']} {s['parish']} {s['place']}")


def _main(argv):
    import config
    import gazetteer as gz
    import volumes
    cfg = config.load()
    rows, _, _ = volumes.run(cfg)
    ra = riksarkivet.Riksarkivet(gz.CACHE / "riksarkivet.json")
    try:
        res = run(rows, ra, set(argv) if argv else None)
    finally:
        ra.save()
    if argv:
        for P in res.values():
            _print(P)
        return
    write_csv(res, config.path(cfg, "residences.csv"))
    n = len(res)
    print(f"{n} people with volume citations: "
          f"{sum(len(P['gaps']) for P in res.values())} gaps, "
          f"{sum(len(P['moves']) for P in res.values())} bracketed moves, "
          f"{sum(1 for P in res.values() if P['uncollated'])} people with stays not yet "
          f"collated as residence events ({sum(len(P['uncollated']) for P in res.values())} stays)")
    print("wrote data/residences.csv")


if __name__ == "__main__":
    _main(sys.argv[1:])
