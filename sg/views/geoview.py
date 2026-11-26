"""
A geographic data view: every located event and record on one map, with
facet filters (as in Calibre's tag browser), a table, and a link scheme so
other views can open it already filtered.

    python3 geoview.py          # writes data/output/geography.html (private: names)

Points: tree events from the tree store (located through place_id, else
their parish) and household-examination citations from volumes.py (one
point per person, volume and page). Each point carries person, event type,
layer (tree / record), years, date precision, place with its whole
hierarchy (place_hierarchy.py), place precision, relationship to the
proband, branch (F/M/FF/FM/MF/MM: the proband's ancestor a
relative is related through, lineage.kinship) and surname. Residences show as stays
(stays.py). Reading of clusters, paths and dates: docs/records.md, "Views".

Link scheme (the part after #, all optional, values comma-separated and
URL-encoded); the page keeps the address in step with the filters:

    person=MH:I1,MH:I2       people (MyHeritage ids)
    lines=1                  draw the path of each selected person (one or two)
    type=residence,birth     event types        layer=tree,record
    branch=FF                family branch (one at a time)
    kin=ancestor,relative    relationship
                             (an address with no filter opens on kin=ancestor;
                             kin=all for every relationship)
    surname=Svenningsson     parish=Källeryd    place=Källeryd/Hagelstorp
    from=1850&to=1900        years (a point counts if its span overlaps)
    q=text                   free text over person, place, detail
    sort=person, sort=-place   the table's order (default: years, earliest first)
    color=branch|type|layer|time|person
                             (none: auto, by person when one to six are chosen,
                             else by branch; by branch, each ancestor takes
                             their own lineage shade, as on the family page)
    open=type,parish         facet groups shown unfolded (default: kin, branch,
                             person; a group in use is always open)
    view=lat,lon,zoom        map position
    bbox=1                   count, list and facets only what is in the map view
                             (the map itself keeps every point)
    sel=born@Hagelstorp      only the people a rule picks, with all their events
                             (pages/shared/rules.js; lifts the ancestors default)
    mark=line@FM,!died       the people a rule picks drawn in colour, the rest
                             faded; rules: born, died, married, lived, at with
                             @place (any level) or :1800-1850; line@, kin@,
                             surname@, name@; commas join, ! negates, a|b either
    sel=step:km>30           steps (lifepath.py) drawn as lines to a dot at the
                             later place: km>, km<, year:, from@, to@, approx
    mark=end:open            loose ends (no death recorded) as open rings: year:,
                             age<, at@, open, none, left, cited, household;
                             person clauses too

A person's path (lines=1) is their life path (lifepath.py): where it
starts, then each step, numbered; links to it (from the family page or a
map popup) show all their points, records included. In the person facet,
"+ spouse" adds the spouse and draws both paths, numbered in date order.
Dates read as written, shortened: ~1850 about, <1850 before, >1850 after,
1850–1860 between or a volume's years.

Sketch: kinship comes from the analysed GEDCOM (config), joined to store
people by MyHeritage id; people only in a newer export show as "unknown".
"""
import html
import re
import sys
from collections import Counter

from sg.common import identity
from sg.common import lineage
from sg.views import viewkit
from sg.views.viewkit import DATE_JS, NAME_JS, embed, nav
from sg.common.intervals import YEAR, years as _span
from sg.records import homes
TAGS = {"BIRT": "birth", "CHR": "baptism", "BAPM": "baptism", "DEAT": "death", "BURI": "burial",
        "CREM": "burial", "MARR": "marriage", "DIV": "divorce", "ENGA": "engagement",
        "RESI": "residence", "OCCU": "occupation", "EDUC": "education", "EMIG": "emigration",
        "IMMI": "immigration", "CENS": "census", "CONF": "confirmation", "NATU": "naturalisation",
        "PROB": "probate", "_MILT": "military", "EVEN": "event", "FACT": "fact", "RETI": "retirement",
        "GRAD": "graduation", "RELI": "religion", "TITL": "title"}


def _precision(date):
    if not date:
        return "none"
    return "day" if re.search(r"\b\d{1,2}\s+[A-Za-z]{3}\b", date) else (
        "year" if YEAR.search(date) else "none")


# a household-examination citation's series -> its event type on the map
RECORD_EVENTS = {"A I": "household examination", "A II a": "household examination",
                 "A II": "household examination", "B": "moving", "B I": "moving in",
                 "B II": "moving out", "C": "birth record", "E I": "marriage record",
                 "F": "death record"}


def collect(cfg):
    from sg.records import gazetteer as gz
    from sg.store import tree_store
    from sg.records import volumes

    store = tree_store.default_store()
    gaz = gz.load(cfg)
    db = store.db
    tree = _tree(cfg)
    people = _people(db, _kinship_by_mh(cfg, tree))
    spouses = _spouses(db)
    pinfo = _place_info(db)
    hier = _hierarchy(db, pinfo)
    fam = {fid: (h, w) for fid, h, w in db.execute("select id, husb, wife from family")}
    points = _tree_points(store, people, pinfo, hier, fam)
    _add_stays(points, pinfo)
    rows, _, report = volumes.run(cfg, riksarkivet_lookups=False)
    points += _record_points(rows, people, gaz, hier)
    used = {pt["p"] for pt in points}
    ppl = {pid: dict(p, spouses=sorted(s for s in spouses.get(pid, ()) if s in used))
           for pid, p in people.items() if pid in used}
    kids = {}
    for f, c in db.execute("select family, child from child"):
        kids.setdefault(f, []).append(c)
    _add_household_leads(ppl, people, fam, kids, _cited_volumes(rows, people))
    return ppl, points, _work_list(cfg, store, tree, report, rows, people, fam, kids, gaz)


def _round(lat, lon):
    return round(lat, 5), round(lon, 5)


def _tree(cfg):
    """The family's GEDCOM tree (family.toml's [gedcom] file)."""
    from sg.common import config
    from sg.readers import gedcom_io
    return gedcom_io.Tree(config.path(cfg, (cfg.get("gedcom") or {})["file"]), **gedcom_io.options(cfg))


def _kinship_by_mh(cfg, tree):
    """MyHeritage id -> (kin, branch, lineage) from the analysed tree (lineage.kinship)."""
    kin = lineage.kinship(tree, (cfg.get("gedcom") or {}).get("proband"))
    by_mh = {}
    for i, p in tree.people.items():
        mh = identity.mh_id(p["facts"])
        if mh:
            by_mh[mh] = kin.get(i, ("unlinked", "", ""))
    return by_mh


def _people(db, by_mh):
    """Store person id -> name, sex, kinship, and birth and death years."""
    from sg.store import tree_store
    people = {}
    for pid, given, surname, sex in db.execute("select id, given, surname, sex from person"):
        k = by_mh.get(pid, ("unknown", "", ""))
        given, surname = tree_store.name_parts(given, surname)   # "okänd" is no surname
        unk = ("" if given else "g") + ("" if surname else "s")
        branch = (k[1] or "").split(" ")[0]
        people[pid] = dict(id=pid, name=f"{given} {surname}".strip(), surname=surname, unk=unk,
                           sex=sex or "", kin=k[0], branch=branch, lineage=k[2])
    for pid, tag, date in db.execute("select owner, tag, date from event where tag in ('BIRT','DEAT')"):
        if pid in people:
            y, _ = _span(date)
            people[pid]["born" if tag == "BIRT" else "died"] = y
    return people


def _spouses(db):
    """person -> the set of their spouses, from families with both partners."""
    spouses = {}
    for fid, h, w in db.execute("select id, husb, wife from family"):
        if h and w:
            spouses.setdefault(h, set()).add(w)
            spouses.setdefault(w, set()).add(h)
    return spouses


def _place_info(db):
    """place id -> (name, parish, kind)."""
    return {pid: (name, parish, kind) for pid, name, parish, kind in
            db.execute("select id, name, parish, kind from place")}


def _hierarchy(db, pinfo):
    """Every place string the tree writes, completed by the others
    (place_hierarchy): "Dädesjö, Uppvidinge" -> "..., Småland, Kronobergs län"."""
    from sg.records import place_hierarchy
    return place_hierarchy.Hierarchy(
        (text, (pid[7:] if pid and pid.startswith("parish:") else pinfo.get(pid, (0, None))[1]))
        for text, pid in db.execute("select place, place_id from event where place is not null"))


def _tree_points(store, people, pinfo, hier, fam):
    """A point per located tree event and person (a family's event: one for each partner)."""
    from sg.store import place_store
    points = []
    for owner, n, tag, typ, date, text, place_id, name, lat, lon, level in \
            place_store.events_with_coords(store):
        if lat is None:
            continue
        who = [owner] if owner in people else [x for x in fam.get(owner, ()) if x]
        y0, y1 = _span(date)
        nm, par, _ = pinfo.get(place_id, (name, None, None))
        if place_id and place_id.startswith("parish:"):
            par = place_id[7:]
        ev = TAGS.get(tag, tag.lower())
        if tag == "EVEN" and typ:
            ev = typ.lower()
        label = hier.label(text or nm or "", par) or nm or text
        lat, lon = _round(lat, lon)
        for p in who:
            points.append(dict(p=p, t=ev, l="tree", y0=y0, y1=y1, d=_precision(date), date=date or "",
                               name=label, parish=par or "", place=place_id or "",
                               lv=level or "", lat=lat, lon=lon, det=text or ""))
    return points


def _add_stays(points, pinfo):
    """Residence entries -> stays (stays.py); both kept, flagged: agg 0 = raw
    entry, 1 = aggregated stay, 2 = anything else."""
    from sg.records import stays as stays_mod
    res = [pt for pt in points if pt["t"] == "residence"]
    for pt in points:
        pt["agg"] = 0 if pt["t"] == "residence" else 2
    by_person = {}
    for pt in res:
        by_person.setdefault(pt["p"], []).append(pt)
    kind = {pid: k for pid, (_, _, k) in pinfo.items()}
    for pid_, pts in by_person.items():
        agg = stays_mod.aggregate(pts, key=lambda q: q["place"] or q["name"])
        first = {st["key"]: st["items"][0] for st in agg}
        # what the place is, not how precisely it is located: a farm without
        # its own point still counts as a farm
        general = lambda k: (not str(k).count("/") or str(k).startswith(("parish:", "osm:"))
                             or kind.get(k) == "rote")
        for st in stays_mod.drop_general(agg, lambda k: first[k]["parish"], general):
            points.append(_stay_point(st))


def _stay_point(st):
    """A stay as a point: its first entry, with the stay's years and a note on what it gathers."""
    q = dict(st["items"][0])
    also = ""
    if st.get("also"):
        also = "also listed as " + ", ".join(dict.fromkeys(a["items"][0]["name"] for a in st.get("also", [])))
    notes = (f"{st['n']} residence entries" if st["n"] > 1 else "",
             f"one of several places in {st['group']}" if st["group"] else "",
             also)
    q.update(y0=st["y0"], y1=st["y1"], date=st["label"], agg=1, n=st["n"],
             d="day" if st["dated"] else ("year" if st["y0"] else "none"),
             det="; ".join(x for x in notes if x))
    return q


def _record_points(rows, people, gaz, hier):
    """Household-examination citations from the volume pipeline: a point per
    person, volume and page, at the farm if the gazetteer knows it, else the parish."""
    points = []
    seen = set()
    for r in rows:
        if r.get("tier") not in ("mh-record", "ra-full", "ra-link") or not r.get("volume"):
            continue
        mh = r.get("mh_id")
        if mh not in people:
            continue
        key = (mh, r["volume"], r.get("page"))
        if key in seen:
            continue
        seen.add(key)
        pid = r.get("place_id") or f"parish:{r.get('parish')}"
        c = gaz.coords(pid)
        if not c:
            continue
        y0, y1 = _span(r.get("ra_years") or r.get("years"))
        ev = RECORD_EVENTS.get(r.get("series", ""), "record")
        name = hier.label(homes.farm_of(r), r.get("parish")) or r.get("parish")
        lat, lon = _round(c[0], c[1])
        points.append(dict(p=mh, t=ev, l="record", agg=2, y0=y0, y1=y1, d="year" if y0 else "none",
                           date=f"{y0}–{y1}" if y0 else "", name=name,
                           parish=r.get("parish", ""), place=r.get("place_id") or "",
                           lv=c[2], lat=lat, lon=lon,
                           det=f"{r['volume']} p. {r.get('page') or '?'}",
                           url=r.get("ra_viewer") or r.get("url") or ""))
    return points


def _cited_volumes(rows, people):
    """person -> {volume code: first page cited}: the volumes each person is
    cited in, located or not."""
    cited = {}
    for r in rows:
        if r.get("volume") and r.get("archive_code") and r.get("series") and r.get("mh_id") in people:
            cited.setdefault(r["mh_id"], {}).setdefault(
                f"{r['archive_code']}/{r['series']}/{r['vol']}", r.get("page") or "?")
    return cited


def _add_household_leads(ppl, people, fam, kids, cited):
    """Each person's cited volumes, and those their household (parents, spouses,
    siblings, children) is cited in: leads for a loose end (trails)."""
    from sg.records import lifepath
    # the household's relations from the tree's families (lifepath.kin_roles),
    # the closest first: a parent's or spouse's household page is likelier
    # to hold the person than a child's or sibling's own
    roles = lifepath.kin_roles(fam, kids)
    rank = {"parent": 0, "spouse": 1, "child": 2, "sibling": 3}
    for pid, p in ppl.items():
        p["cited"] = cited.get(pid, {})
        p["house"] = {}
        near = [(m, k) for m, k in roles.get(pid, {}).items() if k in rank and m in people]
        for m, k in sorted(near, key=lambda x: (rank[x[1]], x[0])):
            word = _role_word(k, people[m]["sex"])
            for c, pg in cited.get(m, {}).items():
                p["house"].setdefault(c, (f"{word} {people[m]['name']}", pg))


def _work_list(cfg, store, tree, report, rows, people, fam, kids, gaz):
    """The errata as work-list tasks (a person's birth, death or burial fix
    read against the store; the family page applies those), age checks on
    the tree (gedcom_audit.misplaced, lives past 105), duplicate citations
    to merge upstream, empty parent slots,
    unresolved places, and gaps in the residences."""
    from sg.views import worklistview
    db = store.db
    tags = {"BIRT": "birth", "DEAT": "death", "BURI": "burial"}
    dates = {(o, tags[t]): d or "" for o, t, d in
             db.execute("select owner, tag, date from event where tag in ('BIRT','DEAT','BURI')")}
    work = worklistview.errata_tasks(report, rows, people, dates)
    work += worklistview.duplicate_tasks(rows, people)
    from sg.readers import gedcom_audit
    noted = {t[0] for t in work if t[5] == "note"}
    xmh = {x: identity.mh_id(p["facts"]) for x, p in tree.people.items()}
    work += worklistview.age_tasks(people, gedcom_audit.misplaced(tree), xmh, noted)
    births = {o: p for o, p in db.execute("select owner, place from event where tag = 'BIRT' and place is not null")}
    work += worklistview.parent_tasks(people, fam, kids, births)
    from sg.common import config
    work += worklistview.gap_tasks(config.path(cfg, "residences.csv"), people)
    work += worklistview.place_tasks(people, *_unresolved(store, rows, fam, gaz))
    return work


def _unresolved(store, rows, fam, gaz):
    """(place string, person) pairs: tree events with no point on the map,
    and citation rows of a place string whose parish is unknown (as the
    gazetteer to-do counts them)."""
    from sg.store import place_store
    unmapped = []
    for owner, _, _, _, _, text, _, _, lat, _, _ in place_store.events_with_coords(store):
        if lat is None and (text or "").strip():
            unmapped += [(text, p) for p in ([owner] if owner not in fam else [x for x in fam[owner] if x])]
    noparish = [(r["event_place"], r.get("mh_id")) for r in rows
                if r.get("event_place") and r.get("tier") == "plac-only" and not gaz.parish(r.get("parish") or "")]
    return unmapped, noparish


def _role_word(role, sex):
    """The word for a relation, by the relative's sex (lifepath.ROLES: male, female, unknown)."""
    from sg.records import lifepath
    return lifepath.ROLES[role][0 if sex == "M" else 1 if sex == "F" else 2]


def pack(people, points, ra=None):
    """Strings into lookup tables, points as arrays: a smaller page. Raw
    residence entries (agg 0) stay out: their stays carry them."""
    points = [pt for pt in points if pt.get("agg", 2) != 0]
    tabs = {k: [] for k in ("t", "l", "d", "parish", "lv", "name", "place")}
    idx = {k: {} for k in tabs}

    def code(k, v):
        v = v or ""
        if v not in idx[k]:
            idx[k][v] = len(tabs[k])
            tabs[k].append(v)
        return idx[k][v]
    pids = sorted(people)
    pidx = {p: i for i, p in enumerate(pids)}
    rows = [[pidx[pt["p"]], code("t", pt["t"]), code("l", pt["l"]), pt["y0"], pt["y1"], code("d", pt["d"]),
             pt["lat"], pt["lon"], code("lv", pt["lv"]), code("name", pt["name"]), code("parish", pt["parish"]),
             code("place", pt["place"]), pt["date"], pt["det"], pt.get("url", ""),
             pt.get("agg", 2), pt.get("n", 1)] for pt in points]
    plist = [[people[p]["id"], people[p]["name"], people[p]["surname"], people[p]["kin"], people[p]["branch"],
              people[p].get("lineage", ""), people[p].get("born"), people[p].get("died"),
              [pidx[s] for s in people[p]["spouses"] if s in pidx], people[p].get("unk", "")] for p in pids]
    codes = {c for p in people.values() for c in (p.get("lineage") or "").split()[:1]}
    col = {c: [lineage.color(c), lineage.color(c, dark=True)] for c in sorted(codes)}
    steps, ends = trails(people, points, ra)
    return dict(tabs=tabs, people=plist, rows=rows, col=col, steps=steps, ends=ends)


def trails(people, points, ra=None):
    """Steps and loose ends (lifepath.py) as rows of the packed points:
    steps [from row, to row, km, approximate 0/1]; ends [row, year last
    seen, age or null, "emigrated" / "moved out" / "", next household
    volume ("code (years)") or "", its viewer, status: "open" (a later
    household volume exists), "none" (the inventory has none), "?" (no
    inventory cached), lead (lifepath.lead: "cited", "household" or ""),
    its page and who ("p. 55, mother Name"); with a lead the volume is the one
    cited]. ra: a Riksarkivet reader, read offline only."""
    from sg.records import lifepath
    at = {id(pt): i for i, pt in enumerate(points)}
    by = {}
    for pt in points:
        by.setdefault(pt["p"], []).append(pt)
    steps, ends = [], []
    for pid in sorted(by):
        path = lifepath.path(by[pid])
        for a, b, km, approx in lifepath.steps(path):
            steps.append([at[id(a)], at[id(b)], km, int(approx)])
        end = lifepath.loose_end(path, people[pid].get("born"), people[pid].get("died"))
        if not end:
            continue
        vol, url, status, lead, note = "", "", "?", "", ""
        parish = end["point"].get("parish")
        if ra and parish and not end["left"]:
            invs = [ra.inventory(a, offline=True) for a in ra.archive_codes(parish, offline=True)]
            if any(i is not None for i in invs):
                nxt = [v for i in invs if i for v in lifepath.next_volumes(i, end["year"])]
                status = "open" if nxt else "none"
                if nxt:
                    vol, url = f"{nxt[0][0]} ({nxt[0][1]})", nxt[0][2]
                lead, hit = lifepath.lead(nxt, people[pid].get("cited"), people[pid].get("house"))
                if hit:
                    (code, years, viewer), pg, who = hit
                    vol, url = f"{code} ({years})", viewer
                    note = f"p. {pg}" + (f", {who}" if who else "")
        ends.append([at[id(end["point"])], end["year"], end["age"], end["left"], vol, url, status, lead, note])
    return steps, ends


def life_steps(people, points, families, children):
    """{person: [[year, date, from, to, km, approximate, [[kind, relative,
    year, relation]]]]}: every life path's steps with their labels
    (lifepath.labels; relation as a word: "uncle", "sister"), for the
    Family view."""
    from sg.records import lifepath
    by = {}
    for pt in points:
        if pt.get("agg", 2) != 0:
            by.setdefault(pt["p"], []).append(pt)
    paths = {pid: lifepath.path(v) for pid, v in by.items()}
    roles = lifepath.kin_roles(families, children)
    life = {pid: (p.get("born"), p.get("died")) for pid, p in people.items()}

    def word(pid, r):
        rel = roles.get(pid, {}).get(r)
        sx = (people.get(r) or {}).get("sex")
        return lifepath.ROLES[rel][0 if sx == "M" else 1 if sx == "F" else 2] if rel else ""
    out = {}
    for pid in sorted(paths):
        rows = [[lifepath.year(b), b.get("date", ""), a.get("name", ""), b.get("name", ""), km, int(ap),
                 [[k, r, y, word(pid, r)] for k, r, y in lab]]
                for a, b, km, ap, lab in lifepath.labels(pid, paths, roles, life)]
        if rows:
            out[pid] = rows
    return out


def write_life_steps(path, people, points):
    """life_steps() from the store's families into a JSON file; returns the
    number of steps."""
    import json
    from sg.store import tree_store
    db = tree_store.default_store().db
    fams = {f: (h, w) for f, h, w in db.execute("select id, husb, wife from family")}
    kids = {}
    for f, c in db.execute("select family, child from child"):
        kids.setdefault(f, []).append(c)
    data = life_steps(people, points, fams, kids)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return sum(len(v) for v in data.values())


SERVED = "The map needs a web server: map tiles are only sent to pages served over http, not to files."


def write(path, data):
    page = HTML.replace("__NAV__", nav("geography.html")).replace("__DATEJS__", DATE_JS + "\n" + NAME_JS + "\n" + viewkit.FOLD_JS + "\n" + viewkit.RULES_JS)
    path.write_text(embed(page.replace("__SERVE__", html.escape(SERVED)), data),
                    encoding="utf-8")


HTML = viewkit.template("geography")
HTML = HTML.replace("__LINEAGE_DARK__", lineage.css_vars(dark=True)).replace("__LINEAGE__", lineage.css_vars())


def _main(argv):
    from sg.common import config
    cfg = config.load()
    people, points, work = collect(cfg)
    from sg.records import gazetteer as gz, riksarkivet
    data = pack(people, points, riksarkivet.Riksarkivet(gz.CACHE / "riksarkivet.json"))
    out = config.path(cfg, "geography.html")
    write(out, data)
    from sg.views import worklistview
    worklistview.write(config.path(cfg, "worklist.html"), data, work)
    n = write_life_steps(out.parent / "life_steps.json", people, points)
    layers = Counter(p["l"] for p in points)
    print(f"geography: {len(points)} points ({', '.join(f'{k} {v}' for k, v in layers.items())}) "
          f"for {len(people)} people -> {out}")
    st = Counter(e[6] for e in data["ends"])
    lead = Counter(e[7] for e in data["ends"])
    print(f"  {len(data['steps'])} steps, {len(data['ends'])} loose ends "
          f"({st['open']} with a later household volume, {st['none']} without, {st['?']} not known; "
          f"leads: {lead['cited']} cited there themselves, {lead['household']} their household)")
    print(f"  {n} steps labelled by the family -> life_steps.json")


if __name__ == "__main__":
    _main(sys.argv[1:])
