"""
The work list (worklist.html): what needs doing, person by person (roadmap,
"Other perspectives"). So far the loose ends only (lifepath.py), each as a
task with what to do next: a citation to place or date (the person is
cited in a later household volume already), a page to open (their
household is), a volume to search, or nothing in the inventory. Written by
the geography step from the loose ends it computes. Private (holds names).
"""
from sg.views import viewkit

# what a loose end asks for, in the order a genealogist would take them
KINDS = [("fix", "place or date the citation: the person is cited in a later household volume, off the path"),
         ("page", "open the page: their household is cited in a later volume"),
         ("search", "search the next household volume of the parish"),
         ("left", "emigrated or moved out: look where they went"),
         ("none", "no later household volume in the inventory"),
         ("unknown", "the parish archive is not in the inventory cache")]


def tasks(data):
    """Loose ends of geoview.pack's data as task rows: [person id, name,
    kin, lineage, born, kind, last seen year, age, event, place, parish,
    volume, viewer, page and who]."""
    tabs, rows, people = data["tabs"], data["rows"], data["people"]
    out = []
    for e in data["ends"]:
        r = rows[e[0]]
        p = people[r[0]]
        kind = ("left" if e[3] else "fix" if e[7] == "cited" else "page" if e[7] == "household"
                else "search" if e[6] == "open" else "none" if e[6] == "none" else "unknown")
        out.append([p[0], p[1], p[3], p[5] or "", p[6], kind, e[1], e[2], e[3] or tabs["t"][r[1]],
                    tabs["name"][r[9]], tabs["parish"][r[10]], e[4], e[5], e[8]])
    return out


def write(path, data):
    page = viewkit.template("worklist").replace("__NAV__", viewkit.nav("worklist.html"))
    path.write_text(viewkit.embed(page.replace("__NAMEJS__", viewkit.NAME_JS + "\n" + viewkit.FOLD_JS),
                                  dict(tasks=tasks(data), kinds=KINDS)), encoding="utf-8")
    return len(data["ends"])
