"""
The family page: one person in focus, their pedigree four generations up (above them)
and their close family around them, read from the tree store. Click anyone
to move the focus; the focus lives in the address, so a person's page can be
bookmarked or opened from another view.

    python3 familyview.py       # writes data/output/family.html (private: names)

Each person shows their years, their lineage codes from the proband (one
per path under pedigree collapse), and counts: tree events, source
citations, and tree-linked or documented matches whose path ends at them.
A parent the tree does not name is drawn as an empty parent slot.
A line on top says how the focus is related to the proband ("wife of
X's 2nd cousin"), by the shortest path that prefers blood to marriage,
with the people along it as links back. Each household row has a lifeline
on one time scale for the page (birth to death, fading where no death is
recorded, a tick for the marriage). Below the references, the descendants:
a row each with their partners, generations indented, lifelines on the
section's own time scale, two generations open (fewer past 250 rows).

Link scheme (after #): p=<store person id>, e.g. #p=MH:I1. Without it the
page opens on the proband.

Sketch: reads the store only (no GEDCOM), except to find the proband's
store id; match counts come from the rebuilt assertion tables.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from sg.common import identity
from sg.common import lineage
from sg.views import viewkit
from sg.common.intervals import years as _span


def lineage_codes(parents, root, depth=12):
    """person -> sorted lineage codes from root ('' for root itself).
    parents: person -> (father, mother), either may be None."""
    codes = defaultdict(list)
    todo = [(root, "")]
    while todo:
        p, c = todo.pop()
        codes[p].append(c)
        if len(c) < depth:
            f, m = parents.get(p, (None, None))
            if f:
                todo.append((f, c + "F"))
            if m:
                todo.append((m, c + "M"))
    return {p: sorted(cs, key=lambda c: (len(c), c)) for p, cs in codes.items()}


ARCHIVAL = ("ra-full", "ra-link", "mh-record", "mh-index", "other")


def references(rows, pages=None):
    """volume_refs rows -> {store id: [[event, date, volume, years, page, url, tier,
    parish, count, other [event, date]s, other urls]]}, one row per volume and
    page, in the shared reference order; citations to other trees only counted."""
    from sg.readers import references as refs
    out, trees = defaultdict(list), defaultdict(int)
    for r in rows:
        pid, tier = r.get("mh_id"), r.get("tier")
        if not pid:
            continue
        if tier == "tree":
            trees[pid] += 1
        elif tier in ARCHIVAL:
            k = refs.order_key(r.get("years"), r.get("parish") or r.get("archive_code"), r.get("series"), r.get("vol"))
            vol = r.get("volume") or r.get("mh_volume") or r.get("source_title") or ""
            out[pid].append((k, [r.get("event", ""), r.get("event_date", ""), vol, r.get("years", ""),
                                 r.get("page", ""), r.get("url") or r.get("ra_viewer") or "", tier,
                                 r.get("parish", "")]))
    res = {}
    for p, v in out.items():
        rows, seen = [], {}
        for _, x in sorted(v, key=lambda t: t[0]):
            # one row per page: the same page cited again, for another event or
            # through another link (MyHeritage's record, Riksarkivet's image),
            # is counted and its event and link added, not repeated
            k = (x[2], x[4]) if x[4] else tuple(x[:5])
            if k in seen:
                r = seen[k]
                r[8] += 1
                if x[0] != r[0] and [x[0], x[1]] not in r[9]:
                    r[9].append([x[0], x[1]])
                if x[5] and x[5] != r[5] and x[5] not in r[10]:
                    r[10].append(x[5])
            else:
                seen[k] = x + [1, [], []]
                rows.append(seen[k])
        for r in rows:
            r.append(page_hint(pages or {}, [r[5]] + r[10], r[4]))
        res[p] = rows
    return res, dict(trees)


def shelf_hints(archive, data_dir):
    """Hints read from the archive shelf (shelf(1)), shown, never stored:
    ({(image series, image): (label, written page, verdict)} from
    archive/pages.tsv, {store id: [[in|out, year, place, text, volume, page,
    verdict]]} from data_dir/moves_read.tsv, {store id: [[column, flag, text,
    volume, page]]} from data_dir/remarks_read.tsv; both written by
    experiments/register_ocr/rows.py). Empty when the files are absent."""
    import csv
    pages, moves = {}, defaultdict(list)
    p = Path(archive) / "pages.tsv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"):
            if r["written"] and r["verdict"].startswith("label differs"):
                pages[(r["volume"], int(r["image"]))] = (r["ra_label"], r["written"], r["verdict"])
    m = Path(data_dir) / "moves_read.tsv"
    if m.exists():
        for r in csv.DictReader(open(m, encoding="utf-8"), delimiter="\t"):
            moves[r["mh_id"]].append([r["dir"], r["year"], r["place"], r["text"], r["volume"], r["page"], r["verdict"]])
    remarks = defaultdict(list)
    m = Path(data_dir) / "remarks_read.tsv"
    if m.exists():
        for r in csv.DictReader(open(m, encoding="utf-8"), delimiter="\t"):
            remarks[r["mh_id"]].append([r["column"], r["flag"], r["text"], r["volume"], r["page"]])
    return pages, dict(moves), dict(remarks)


def page_hint(pages, urls, cited):
    """'p. 407 written on this image (labelled 406)' for a reference whose
    image the shelf read a different page number on."""
    for u in urls:
        m = re.search(r"bildvisning/([A-Za-z]?\d+)_(\d+)", u or "")
        if m and (m.group(1), int(m.group(2))) in pages:
            label, written, _ = pages[(m.group(1), int(m.group(2)))]
            if cited and cited in written.split("-"):
                return ""
            return f"p. {written} written on this image (labelled {label or 'without a page'})"
    return ""


def person_fixes(fixes):
    """errata [[fix]] entries on a person's birth or death -> {store id: {field: entry}}."""
    out = defaultdict(dict)
    for f in fixes:
        k, field = f.get("key", ""), f.get("field", "")
        if k.startswith("person:") and field in ("birth", "death"):
            out[k[7:]][field] = f
    return out


def added(db, notes=(), fixes=()):
    """Per person, what is kept beside MyHeritage, for the "Notes and added
    sources" section: errata fixes and notes keyed person:<id>, and citations
    added in the store (source, page, and the reason given, which quotes the
    record). Rows: [kind, date, head, text, image id]."""
    out = defaultdict(list)
    for e in fixes:
        k = e.get("key", "")
        if k.startswith("person:"):
            out[k[7:]].append(["fix", str(e.get("date", "")),
                               f"{e.get('field', '')}: {e.get('was') or '—'} → {e.get('now', '')}",
                               e.get("source", ""), ""])
    why = {}
    try:
        db.execute("select at, what, why from change limit 0")
        db.execute("select origin, source, page, event from citation limit 0")
    except Exception:                          # a store without edits: notes and fixes only
        db = None
    for at, what, w in (db.execute("select at, what, why from change") if db else ()):
        m = re.match(r"(\S+): cited (\S+)(?: (.*?))?(?: on event \d+)?$", what or "")
        if m:
            why[(m[1], m[2], m[3] or "")] = ((at or "")[:10], w or "")
    tags = dict(BIRT="birth", CHR="baptism", DEAT="death", BURI="burial", MARR="marriage", RESI="residence")
    seen = {}
    for owner, src, page, title, tag in (db.execute(
            "select c.owner, c.source, coalesce(c.page, ''), s.title, e.tag from citation c"
            " join source s on s.id = c.source left join event e on e.n = c.event"
            " where c.origin like 'edit:%' order by c.n") if db else ()):
        key, tag = (owner, src, page), tags.get(tag, (tag or "").lower())
        if key in seen:                      # one row per source and page, its events listed
            if tag and tag not in seen[key][2]:
                seen[key][2] = seen[key][2].replace(" — ", f", {tag} — ", 1)
            continue
        at, w = why.get(key, ("", ""))
        img = re.search(r"bild ([A-Za-z]?\d+_\d+)", page)
        seen[key] = row = ["src", at, f"{tag or 'person'} — {title}{'; ' + page if page else ''}", w,
                           img.group(1) if img else ""]
        out[owner].append(row)
    for e in notes:
        k = e.get("key", "")
        if k.startswith("person:"):
            out[k[7:]].append(["note", str(e.get("date", "")), "", e.get("text", ""), ""])
    return out


def collect(db, root, ref_rows=(), fixes=(), notes=(), hints=({}, {}, {}), steps=None):
    """The lens's data from a store connection; root is the proband's store id;
    ref_rows: the volume_refs rows (volumes.py), for the references section;
    fixes: errata [[fix]] entries, of which a person's birth and death apply
    while the store still says what the erratum calls `was`."""
    from sg.store import tree_store
    people = {}
    for pid, g, s, sex in db.execute("select id, given, surname, sex from person"):
        g, s = tree_store.name_parts(g, s)    # unknown parts absent; unk says which
        people[pid] = dict(name=f"{g} {s}".strip(), sex=sex or "", unk=("" if g else "g") + ("" if s else "s"), gl=len(g))
    for pid, tag, date in db.execute("select owner, tag, date from event where tag in ('BIRT','DEAT')"):
        if pid in people:
            k = "b" if tag == "BIRT" else "d"
            people[pid][k], people[pid][k + "r"] = _span(date)[0], date or ""
            if tag == "DEAT":                  # a death known, dated or not ("1 DEAT Y")
                people[pid]["dk"] = 1
    pfx = person_fixes(fixes)
    applied = defaultdict(list)
    for pid, fs in pfx.items():
        for field, f in fs.items():
            k = "b" if field == "birth" else "d"
            if pid in people and people[pid].get(k + "r", "") == (f.get("was") or ""):
                people[pid][k], people[pid][k + "r"] = _span(f["now"])[0], f["now"]
                applied[pid].append((field, f))
    fams = {fid: dict(h=h, w=w, c=[]) for fid, h, w in db.execute("select id, husb, wife from family")}
    for fid, child in db.execute("select family, child from child order by rowid"):
        if fid in fams:
            fams[fid]["c"].append(child)
    for owner, tag, date in db.execute("select owner, tag, date from event where tag in ('MARR', 'DIV')"):
        if owner in fams and date:
            if tag == "MARR" and "m" not in fams[owner]:
                fams[owner]["m"], fams[owner]["mr"] = _span(date)[0], date
            elif tag == "DIV":
                fams[owner].setdefault("dv", _span(date)[0])
    parents = {}
    for f in fams.values():
        for c in f["c"]:
            parents.setdefault(c, (f["h"], f["w"]))
    codes = lineage_codes(parents, root)
    nev = dict(db.execute("select owner, count(*) from event group by owner"))
    ncit = dict(db.execute("select owner, count(*) from citation group by owner"))
    # matches whose documented or tree path ends at this ancestor (one count per match)
    by_code = defaultdict(set)
    for t in ("out_assertions_tree", "out_assertions_documented"):
        try:
            for lin, mk in db.execute(f"select lineage, match_key from {t}"):
                by_code[lin].add(mk)
        except Exception:
            pass
    linked = defaultdict(int)
    for (pid,) in db.execute("select person from dna_match where person is not null and person != ''"):
        linked[pid] += 1
    out = []
    for pid, p in people.items():
        cs = codes.get(pid, [])
        dna = len(set().union(*(by_code.get(c, set()) for c in cs))) if cs else 0
        out.append([pid, p["name"], p["sex"], p.get("b"), p.get("d"), cs,
                    nev.get(pid, 0), ncit.get(pid, 0), dna, linked.get(pid, 0), p.get("br", ""), p.get("dr", ""), p.get("dk", 0), p["unk"], p["gl"]])
    life = defaultdict(list)
    for owner, tag, date, place, value, parish in db.execute(
            # a place from the store alone (records placed it, the tree has no
            # text) is named with its parish: "Gyllenfors, Anderstorp"
            "select e.owner, e.tag, e.date, coalesce(nullif(e.place, ''), p.name ||"
            " case when p.parish is not null and p.parish != p.name then ', ' || p.parish else '' end), e.value,"
            " coalesce(p.parish, case when e.place_id like 'parish:%' then substr(e.place_id, 8) end)"
            " from event e left join place p on p.id = e.place_id order by e.owner, e.n"):
        if owner in people:
            # GEDCOM's "Y" only says the event happened: the row itself says that
            life[owner].append([tag, date or "", place or "", "" if value == "Y" else value or "", None, parish or ""])
    for pid, fs in applied.items():
        for field, f in fs:
            tag = "BIRT" if field == "birth" else "DEAT"
            life[pid] = [e for e in life[pid] if e[0] != tag] + [
                [tag, f["now"], "", "erratum: " + f.get("source", ""), None, ""]]
    refs, trees = references(ref_rows, hints[0])
    col = {c: [lineage.color(c), lineage.color(c, dark=True)] for cs in codes.values() for c in cs if c}
    return dict(root=root, people=out, life=life, refs=refs, trees=trees, col=col,
                added=added(db, notes, fixes), moves={k: v for k, v in hints[1].items() if k in people},
                remarks={k: v for k, v in (hints[2] if len(hints) > 2 else {}).items() if k in people},
                steps={k: v for k, v in (steps or {}).items() if k in people},
                fams=[[fid, f["h"], f["w"], f["c"], f.get("m"), f.get("mr", ""), f.get("dv")] for fid, f in fams.items()])


def proband_id(cfg):
    from sg.readers import gedcom_io
    tree, proband = gedcom_io.load(cfg)
    x = tree.id(proband)
    return identity.mh_id(tree.people[x]["facts"]) or "MH:" + x.strip("@")


def write(path, data):
    path.write_text(viewkit.embed(HTML.replace("__NAV__", viewkit.nav("family.html"))
                                  .replace("__DATEJS__", viewkit.DATE_JS + "\n" + viewkit.NAME_JS)
                                  .replace("__FOLDJS__", viewkit.FOLD_JS + viewkit.OFFLINE_JS), data),
                    encoding="utf-8")


HTML = viewkit.template("family")
HTML = HTML.replace("__LINEAGE_DARK__", lineage.css_vars(dark=True)).replace("__LINEAGE__", lineage.css_vars())


def _main(argv):
    from sg.common import config
    from sg.store import tree_store
    cfg = config.load()
    store = tree_store.default_store()
    import csv
    vr = config.path(cfg, "volume_refs.csv")
    rows = list(csv.DictReader(open(vr, encoding="utf-8"))) if vr.exists() else []
    from sg.records import errata
    er = errata.load(config.path(cfg, "errata.toml"))
    out = config.path(cfg, "family.html").parent        # the output folder; the shelf beside it, as serve.py
    hints = shelf_hints(out.parent / "archive", out)
    ls = out / "life_steps.json"        # Geography's steps, labelled by the family (geoview.life_steps)
    steps = json.loads(ls.read_text(encoding="utf-8")) if ls.exists() else {}
    data = collect(store.db, proband_id(cfg), rows, er["fix"], er["note"], hints, steps)
    path = config.path(cfg, "family.html")
    write(path, data)
    print(f"{len(data['people'])} people, {len(data['fams'])} families -> {path}")


if __name__ == "__main__":
    _main(sys.argv[1:])
