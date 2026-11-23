"""
Where the cited people sat, read from the volume rows volumes.py builds:
one farm across volumes (page by page, who is cited there), and the
parental household at birth (which household-examination volume and page
should show each person as a newborn in their parents' home, and whether
the tree cites it). Run through `volumes.py farm|home` (volumes(1)).
"""
import re
from collections import Counter, defaultdict

from sg.readers import gedcom_io
from sg.records import riksarkivet


def farm_index(rows):
    """farm -> volume -> sorted pages, with people per page."""
    idx = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        farm = (r.get("place") or r.get("farm") or "").strip()
        if not farm or not r.get("parish"):
            continue
        vol = r["volume"] or f"{r['parish']} (no volume)"
        idx[f"{farm}, {r['parish']}"][vol][r.get("page") or ""].append(r)
    return idx


# -- the parental household at birth -----------------------------------------------

HOME_SERIES = ("A I", "A II a")         # household examinations, parish registers


def _span(s):
    ys = [int(y) for y in re.findall(r"1[5-9]\d\d", s or "")]
    return (min(ys), max(ys)) if ys else None


def _covers(s, y):
    sp = _span(s)
    return bool(sp and sp[0] <= y <= sp[1])


def _same_farm(a, b):
    """Rows a and b on one farm: the same gazetteer place, or one written
    name inside the other ("Jettingstad" ~ "Jettingstad Mellangård")."""
    if a.get("place_id") and a.get("place_id") == b.get("place_id"):
        return True
    from sg.records import gazetteer as gz
    fa, fb = (gz.fold(r.get("place") or r.get("farm") or "") for r in (a, b))
    return bool(fa and fb) and (fa in fb or fb in fa)


def birth_column_reader(gaz):
    def parish_of(written, here):
        """The household books' birth column -> (parish, place id or "").
        Read alone when firm; else within the record's own parish
        ("Källerö" in a Källeryd book; "Adel." for Adelöv). Lone names
        from the full parish list only when longer than five letters
        ("Åby" in an Östergötland book is Stora Åby, not Åby). Unvalidated."""
        w, how = gaz.explain_plac(written)[:2]
        w = w or ""
        firm = (how.startswith("parish only") and "farm part unknown" not in how) or \
            how in ("plac_map", "unique village name") or (w and not w.startswith("parish:")) or \
            (how == "parish list, lone name" and len(written.strip(" .")) > 5)
        if w and firm:
            return (w[7:], "") if w.startswith("parish:") else ((gaz.places.get(w) or {}).get("parish", ""), w)
        if here:
            w = gaz.explain_plac(f"{written}, {here}")[0] or ""
            if w and not w.startswith("parish:") and (gaz.places.get(w) or {}).get("parish") == here:
                return here, w
            short = written.strip(" .").lower()
            if len(short) >= 3 and here.lower().startswith(short):
                return here, ""
        return "", ""
    return parish_of


def homes(rows, parents, ra, people=None, offline=True, parish_of=None):
    """Where to look for each person in their parents' household at birth.

    `people`: person ids to look at (default: every ancestor with a birth
    parish). A person counts as found when they or a parent have a
    household row (HOME_SERIES) of the birth parish covering the birth
    year. For the rest: the birth parish's A I volumes covering the year
    (or the next, for a birth late in a book's span), from Riksarkivet's
    inventory of the archive; per volume, the farms to look at (the birth
    farm, then the parents' farms in that parish from their nearest
    household rows) with the page others on that farm are cited at in
    that volume, or else a page in another volume as a hint (books were
    often copied in farm order). `parish_of(written place, record's
    parish) -> (parish, place id)`
    reads the household books' birth column (the `born` field): it stands
    in for a missing birth parish, and a parish it gives that differs from
    the tree's is reported. Returns a list of dicts."""
    by_person = defaultdict(list)
    for r in rows:
        by_person[r["person"]].append(r)
    archive_of = Counter()
    for r in rows:
        if r.get("parish") and r.get("archive_code"):
            archive_of[(r["parish"], r["archive_code"])] += 1
    arch = {}
    for (p, a), _ in archive_of.most_common():
        arch.setdefault(p, a)
    on_farm = defaultdict(list)          # volume code -> household rows with a farm
    for r in rows:
        if r.get("series") in HOME_SERIES and r.get("ra_code") and (r.get("farm") or r.get("place")):
            on_farm[r["ra_code"]].append(r)
    if people is None:
        people = sorted({r["person"] for r in rows if r.get("kin") == "ancestor"})
    out = []
    for i in people:
        rs = by_person.get(i, [])
        birth = next((r for r in rs if r["event"] in ("birth", "baptism") and r.get("parish")
                      and _span(r.get("event_date"))), None)
        # the household books' own birth column ("Födelse: 5 okt 1929 - Habo skb.")
        said = Counter()
        for r in rs:
            d, _, pl = (r.get("born") or "").partition(" - ")
            q, pid = parish_of(pl.strip(), r.get("parish", "")) if parish_of and pl.strip() else ("", "")
            if q and _span(d):
                said[(q, _span(d)[1], pid)] += 1
        if not birth and said:
            (q, yy, pid), n = said.most_common(1)[0]
            farm = pid.split("/", 1)[1] if "/" in pid else ""
            birth = dict(rs[0], event="birth", parish=q, event_date=str(yy), place=farm, farm=farm,
                         place_id=pid, event_place=f"{farm + ', ' if farm else ''}{q} "
                         f"(household books' birth column, {n} record{'s' * (n > 1)})")
        if not birth:
            continue
        y, parish = _span(birth["event_date"])[1], birth["parish"]
        fam = [i] + list(parents.get(i, []))
        house = [r for p in fam for r in by_person.get(p, [])
                 if r.get("series") in HOME_SERIES and r.get("parish") == parish and r.get("volume")]
        hit = [r for r in house if _covers(r.get("years") or r.get("ra_years"), y)]
        item = dict(person=i, label=birth.get("label", i), year=y, parish=parish,
                    birth_place=birth.get("event_place", ""), farm=birth.get("place") or birth.get("farm") or "",
                    parents=[p for p in fam[1:]], books_say=sorted({q for q, *_ in said if q != parish}), found=sorted({f"{r['volume']} p.{r.get('page') or '?'}"
                                                              for r in hit}), volumes=[])
        out.append(item)
        if hit:
            continue
        # farms to look at: the birth farm, then the parents' nearest farms
        farms = [birth] if birth.get("place") or birth.get("farm") else []
        for (q, _, pid), _n in said.most_common():
            if q != parish or "/" not in pid:
                continue
            f = dict(place=pid.split("/", 1)[1], place_id=pid, why="books' birth column")
            if not any(_same_farm(f, g) for g in farms):
                farms.append(f)
        near = sorted((r for r in house if r["person"] != i and (r.get("farm") or r.get("place"))
                       and _span(r.get("years") or r.get("ra_years"))),
                      key=lambda r: min(abs(v - y) for v in _span(r.get("years") or r.get("ra_years"))))
        for r in near:
            if not any(_same_farm(r, f) for f in farms):
                farms.append(r)
            if len(farms) >= 3:
                break
        archive = arch.get(parish) or next(iter(ra.archive_codes(parish, offline=offline) if ra else []), "")
        inv = (ra.inventory(archive, offline=offline) if ra and archive else None) or {}
        vols = [v for c, v in inv.items() if f"/{HOME_SERIES[0]}/" in c and _covers(v.get("years"), y)]
        if not vols or _span(vols[0]["years"])[1] == y:
            vols += [v for c, v in inv.items() if f"/{HOME_SERIES[0]}/" in c
                     and _covers(v.get("years"), y + 1) and v not in vols]
        if not vols:                       # no book yet: the first within 15 years, child at home
            later = sorted((v for c, v in inv.items() if f"/{HOME_SERIES[0]}/" in c and _span(v.get("years"))
                            and y < _span(v["years"])[0] <= y + 15), key=lambda v: _span(v["years"])[0])
            vols = later[:1]
        item["archive"] = archive
        # the birth entry names the parents' farm: the C volume(s) of the year
        item["births"] = [dict(code=v["code"], years=v.get("years", ""), viewer=v.get("viewer", ""),
                               images=v.get("images", ""))
                          for c, v in inv.items() if re.search(r"/C(?: I)?/", c) and _covers(v.get("years"), y)]
        for v in vols:
            looks = []
            for f in farms:
                same = [r for r in on_farm.get(v["code"], []) if _same_farm(r, f)]
                pages = sorted({r["page"] for r in same if r.get("page")}, key=lambda p: int(p) if p.isdigit() else 0)
                hint = []
                if not pages:
                    other = defaultdict(set)
                    for c, rs2 in on_farm.items():
                        if c.rsplit("/", 1)[0] == v["code"].rsplit("/", 1)[0] and c != v["code"]:
                            for r in rs2:
                                if _same_farm(r, f) and r.get("page"):
                                    other[(r.get("years") or r.get("ra_years"), r["volume"])].add(r["page"])
                    sp = _span(v["years"])
                    hint = sorted(other.items(), key=lambda kv: abs((_span(kv[0][0]) or sp)[0] - sp[0]))[:2]
                looks.append(dict(farm=f.get("place") or f.get("farm"), why="birth" if f is birth else f.get("why", "parents"),
                                  pages=pages, who=sorted({r["label"] for r in same})[:3],
                                  hint=[(vol, yrs, sorted(ps)) for (yrs, vol), ps in hint]))
            item["volumes"].append(dict(code=v["code"], years=v.get("years", ""), viewer=v.get("viewer", ""),
                                        images=v.get("images", ""), looks=looks))
    return out


def print_farms(rows, pattern):
    """volumes.py farm: every farm matching pattern, volume by volume."""
    rx = re.compile(pattern, re.I)
    for farm, vols in sorted(farm_index(rows).items()):
        if not rx.search(farm):
            continue
        print(farm)
        for vol, pages in sorted(vols.items()):
            for page, rs in sorted(pages.items(), key=lambda kv: int(kv[0] or 0)):
                people = sorted({f"{r['label']} [{r['kin']}{' ' + r['branch'] if r['branch'] else ''}]"
                                 for r in rs})
                print(f"  {vol:32} p.{page or '?':>4}  " + "; ".join(people))


def print_homes(cfg, rows, pattern="", offline=True):
    """volumes.py home: where to find each person in the household at birth
    (pattern: only people whose label matches; else those not yet found)."""
    from sg.common import config
    from sg.records import gazetteer as gz
    g = cfg.get("gedcom") or {}
    tree = gedcom_io.Tree(config.path(cfg, g["file"]), **gedcom_io.options(cfg))
    ra = riksarkivet.Riksarkivet(gz.CACHE / "riksarkivet.json")
    gaz = gz.load(cfg)

    parish_of = birth_column_reader(gaz)
    people = None
    if pattern:
        rx = re.compile(pattern, re.I)
        people = sorted({r["person"] for r in rows if rx.search(r.get("label") or "")})
    out = homes(rows, {i: tree.parents(i) for i in tree.people}, ra, people,
                offline=offline, parish_of=parish_of)
    ra.save()
    for o in out:
        if o["found"] and people is None:
            continue
        print(f"{o['label']}  ✻ {o['year']} {o['birth_place'] or o['parish']}  "
              f"({len(o['parents'])} parent{'s' * (len(o['parents']) != 1)} in the tree)")
        if o["books_say"]:
            print("  household books give the birth parish as " + ", ".join(o["books_say"]))
        if o["found"]:
            print("  found: " + "; ".join(o["found"]))
            continue
        if not o.get("archive"):
            print("  no archive known for this parish")
        for b in o.get("births", []):
            print(f"  births {b['code']} ({b['years']})  {b['viewer']}")
        for v in o["volumes"]:
            print(f"  home   {v['code']} ({v['years']})  {v['viewer']}")
            for lk in v["looks"]:
                where = (f"p. {', '.join(lk['pages'])} (cited there: {'; '.join(lk['who'])})" if lk["pages"]
                         else "; ".join(f"p. {', '.join(ps)} in {vol} ({yrs})" for vol, yrs, ps in lk["hint"])
                         or "not cited in this archive")
                print(f"         {lk['farm']} ({lk['why']}): {where}")
        if not o["volumes"] and o.get("archive"):
            print("  no household volume for the year in the archive's inventory")
    left = [o for o in out if not o["found"]]
    print(f"{len(out)} with a birth parish; {len(out) - len(left)} found in a household "
          f"record covering the birth year; {len(left)} to look for")
