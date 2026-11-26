"""
The work list (worklist.html): what needs doing, person by person (roadmap,
"Other perspectives"). So far two sources. The loose ends (lifepath.py),
each with what to do next: a citation to place or date (the person is
cited in a later household volume already), a page to open (their
household is), a volume to search, or nothing in the inventory. The errata
(errata.py), by their state against the current export: a fix still
waiting upstream in MyHeritage, one the export now has (the entry can go),
a conflict, an orphan, an open note. Age checks (gedcom_audit.misplaced:
a parent too young or too old at a birth, a child born after a parent's
death or before a marriage while an earlier partner lived; and a life
past 105), skipped for a person an erratum note already covers. Unresolved places, one task per place
string with its people: a tree event that reaches no point on the map, and
a Swedish place string no parish is known for (the gazetteer to-do's
list). Empty parent slots (an ancestor with
no parents in the tree, anyone with one parent of two), and the gaps
between record stays (residences.py's residences.csv, written just before)
with the volumes to open. Written by the geography step. Private (holds
names).
"""
from sg.views import viewkit

# what a loose end asks for, in the order a genealogist would take them
KINDS = [("conflict", "errata: the export says neither what the fix calls was nor now; check which is right"),
         ("orphan", "errata: the key matches nothing in the export any more; re-key or drop the entry"),
         ("upstream", "errata: fixed here, still to correct in MyHeritage"),
         ("duplicate", "a MyHeritage record citing the page a Riksarkivet citation cites: merge or drop it in MyHeritage"),
         ("retire", "errata: MyHeritage now says what the fix says; the entry can go"),
         ("age", "an age check: a parent too young or old at the birth, a child after a parent's death, a life past 105; perhaps under the wrong union"),
         ("cited", "loose end: place or date the citation, the person is cited in a later household volume, off the path"),
         ("page", "loose end: open the page, their household is cited in a later volume"),
         ("place", "an unresolved place: not on the map, or no parish known; add it to the gazetteer or data/plac_map.toml"),
         ("parent", "an empty parent slot: an ancestor with no parents in the tree, or a parent missing beside the other"),
         ("gap", "a gap between record stays: open the household volumes in between"),
         ("search", "loose end: search the next household volume of the parish"),
         ("note", "errata: an open note or question"),
         ("left", "loose end: emigrated or moved out, look where they went"),
         ("none", "loose end: no later household volume in the inventory"),
         ("unknown", "loose end: the parish archive is not in the inventory cache")]
LIFE = {"birth", "death", "burial"}


def tasks(data):
    """Loose ends of geoview.pack's data as task rows: [person id, name,
    kin, lineage, born, kind, last seen year, age, event, place, parish,
    volume, viewer, page and who]."""
    tabs, rows, people = data["tabs"], data["rows"], data["people"]
    out = []
    for e in data["ends"]:
        r = rows[e[0]]
        p = people[r[0]]
        kind = ("left" if e[3] else "cited" if e[7] == "cited" else "page" if e[7] == "household"
                else "search" if e[6] == "open" else "none" if e[6] == "none" else "unknown")
        out.append([p[0], p[1], p[3], p[5] or "", p[6], kind, e[1], e[2], e[3] or tabs["t"][r[1]],
                    tabs["name"][r[9]], tabs["parish"][r[10]], e[4], e[5], e[8]])
    return out


def errata_tasks(report, rows, people, dates):
    """errata.apply's report as task rows, in the loose ends' shape: [person
    id, name, kin, lineage, born, kind, date entered, None, what ("death:
    1838 → 29 OCT 1838", or "note"), key, "", the note or the fix's source,
    "", ""]. The person is the key's, or the first citation row's that
    answers to it. A person's birth, death or burial fix (applied by the
    family page, so the report cannot judge it) is read against dates
    {(person, field): the store's date}."""
    from sg.records import errata
    owner = {}
    for r in rows:
        for k in errata.keys(r):
            owner.setdefault(k, r.get("mh_id"))
    out = []
    for e, status, _ in report:
        key, f = e.get("key", ""), e.get("field")
        pid = key[7:] if key.startswith("person:") else owner.get(key)
        if "field" in e and f in LIFE and key.startswith("person:"):
            cur, was, now = dates.get((pid, f), ""), str(e.get("was", "")), str(e.get("now", ""))
            kind = "retire" if cur == now else "upstream" if cur == was else "conflict"
        else:
            kind = {"applied": "upstream", "retired": "retire", "orphan": "orphan",
                    "attached": "note"}.get(status, "conflict")
        what = f"{f}: {e.get('was') or '—'} → {e.get('now', '')}" if "field" in e else "note"
        out.append(_row(pid, people, kind, str(e.get("date", "")), what, key,
                        e.get("text", "") if "field" not in e else e.get("source", "")))
    return out


def _row(pid, people, kind, when, what, key, text):
    p = people.get(pid) or {}
    return [pid or "", p.get("name", ""), p.get("kin", ""), p.get("lineage", ""), p.get("born"),
            kind, when, None, what, key, "", text, "", ""]


def duplicate_tasks(rows, people):
    """A MyHeritage record cited beside a Riksarkivet citation of the same
    entry (volumes.mark_same_citations): one task per person and page, to
    merge upstream. MyHeritage's own copies (Swedish and English site) are
    only collapsed, not listed."""
    out, seen = [], set()
    for r in rows:
        lead = r.get("same_as", "")
        if r.get("tier") != "mh-record" or not lead.startswith("ra-"):
            continue
        k = (r.get("mh_id"), lead)
        if k not in seen:
            seen.add(k)
            out.append(_row(r.get("mh_id"), people, "duplicate", r.get("years", ""),
                            f"{r.get('volume', '')} p. {r.get('page', '')} (MyHeritage, {r.get('source_title', '')})",
                            r.get("event", ""), f"same as {lead}"))
    return out


def age_tasks(people, misplaced=(), xref_to_id=None, skip=()):
    """Age checks: gedcom_audit.misplaced's children perhaps under the wrong
    union (with the parent's other unions as the next hint), and lives past
    105 from the people's birth and death years. skip: people already
    covered by an erratum note."""
    xref_to_id = xref_to_id or {}
    out = []
    for m in misplaced:
        pid = xref_to_id.get(m.get("xref"))
        if pid in skip:
            continue
        out.append(_row(pid, people, "age", str((people.get(pid) or {}).get("born") or ""), m["why"], m["union"],
                        ("other unions: " + "; ".join(m["candidates"])) if m.get("candidates") else ""))
    for pid, p in people.items():
        b, d = p.get("born"), p.get("died")
        if b is not None and d is not None and d - b > 105 and pid not in skip:
            out.append(_row(pid, people, "age", str(b), f"a life of {d - b} years", "", f"born {b}, died {d}"))
    return out


KIN_ORDER = ["ancestor", "relative", "spouse of relative"]
SWEDISH = ("sverige", "sweden", " län")


def place_tasks(people, unmapped=(), noparish=()):
    """One task per unresolved place string: unmapped, (string, person) for
    each tree event with no point; noparish, (string, person) for each
    Swedish place string with no known parish. The person shown is the one
    nearest the proband; the text names how many events and people."""
    near = lambda pid: (KIN_ORDER.index(people.get(pid, {}).get("kin")) if people.get(pid, {}).get("kin") in KIN_ORDER
                        else 9, len((people.get(pid, {}).get("lineage") or "x").split()[0]), pid or "")
    out = []
    for why, pairs in (("not on the map", unmapped),
                       ("no parish known", [(s, p) for s, p in noparish if any(w in s.lower() for w in SWEDISH)])):
        by = {}
        for s, pid in pairs:
            by.setdefault(s, []).append(pid)
        for s, pids in by.items():
            who = sorted(set(pids), key=near)
            out.append(_row(who[0], people, "place", "", s, why,
                            f"{len(pids)} event{'s' if len(pids) > 1 else ''}, {len(who)} "
                            f"{'people' if len(who) > 1 else 'person'}"))
    return out


def parent_tasks(people, families, children, births=None):
    """Empty parent slots: an ancestor with no parents in the tree, and
    anyone whose parents' family has one parent of two. families: {family:
    (husband, wife)}; children: {family: [children]}; births: {person: birth
    place as written}, the next hint."""
    births = births or {}
    of = {}
    for f, ks in children.items():
        for k in ks:
            of.setdefault(k, []).append(families.get(f, (None, None)))
    out = []
    for pid, p in people.items():
        fams = of.get(pid)
        if not fams:
            if p.get("kin") == "ancestor":
                out.append(_row(pid, people, "parent", str(p.get("born") or ""), "both parents unknown", "",
                                births.get(pid, "")))
            continue
        h, w = fams[0]
        if bool(h) != bool(w):
            out.append(_row(pid, people, "parent", str(p.get("born") or ""),
                            "mother unknown" if h else "father unknown", "", births.get(pid, "")))
    return out


def gap_tasks(path, people):
    """The gaps between record stays in residences.csv (residences.py),
    with the volumes it names to open."""
    import csv
    from pathlib import Path
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [_row(r["mh_id"], people, "gap", f"{r['start']}–{r['end']}", r["place"], "", r["detail"])
                for r in csv.DictReader(f) if r["kind"] == "gap"]


def write(path, data, work=()):
    page = viewkit.template("worklist").replace("__NAV__", viewkit.nav("worklist.html"))
    path.write_text(viewkit.embed(page.replace("__NAMEJS__", viewkit.NAME_JS + "\n" + viewkit.FOLD_JS),
                                  dict(tasks=tasks(data) + list(work), kinds=KINDS)), encoding="utf-8")
    return len(data["ends"]) + len(work)
