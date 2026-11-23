"""
The work list (worklist.html): what needs doing, person by person (roadmap,
"Other perspectives"). So far two sources. The loose ends (lifepath.py),
each with what to do next: a citation to place or date (the person is
cited in a later household volume already), a page to open (their
household is), a volume to search, or nothing in the inventory. The errata
(errata.py), by their state against the current export: a fix still
waiting upstream in MyHeritage, one the export now has (the entry can go),
a conflict, an orphan, an open note. Written by the geography step, which
has both at hand. Private (holds names).
"""
from sg.views import viewkit

# what a loose end asks for, in the order a genealogist would take them
KINDS = [("conflict", "errata: the export says neither what the fix calls was nor now; check which is right"),
         ("orphan", "errata: the key matches nothing in the export any more; re-key or drop the entry"),
         ("upstream", "errata: fixed here, still to correct in MyHeritage"),
         ("retire", "errata: MyHeritage now says what the fix says; the entry can go"),
         ("cited", "loose end: place or date the citation, the person is cited in a later household volume, off the path"),
         ("page", "loose end: open the page, their household is cited in a later volume"),
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
        p = people.get(pid) or {}
        out.append([pid or "", p.get("name", ""), p.get("kin", ""), p.get("lineage", ""), p.get("born"),
                    kind, str(e.get("date", "")), None, what, key, "",
                    e.get("text", "") if "field" not in e else e.get("source", ""), "", ""])
    return out


def write(path, data, work=()):
    page = viewkit.template("worklist").replace("__NAV__", viewkit.nav("worklist.html"))
    path.write_text(viewkit.embed(page.replace("__NAMEJS__", viewkit.NAME_JS + "\n" + viewkit.FOLD_JS),
                                  dict(tasks=tasks(data) + list(work), kinds=KINDS)), encoding="utf-8")
    return len(data["ends"]) + len(work)
