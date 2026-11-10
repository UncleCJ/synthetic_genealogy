"""
Errata and notes kept beside the master data (MyHeritage), never in it.

Each entry names *what* it is about by a key that survives re-exports,
records what the export said when it was written (`was`), and what it
should say (`now`). Every run checks each entry against the current
export:

    applied   the export still says `was`: the correction is applied
    retired   the export now says `now`: fixed upstream, the entry can go
    conflict  the export says something else: look again
    orphan    nothing in the export has this key any more

so corrections can be made in MyHeritage at leisure, and the side file
shrinks as they land there. Notes have no `was`/`now`; they are attached
to whatever carries the key and shown with it.

Keys (one row can carry several):

    mh:<itemId>          a MyHeritage record (household examination etc.)
    bild:<imageid_no>    a Riksarkivet image, e.g. bild:C0022433_00223
    volume:<refcode>     a volume, e.g. volume:SE/VALA/00221/A I/20
    person:<MH:I123>     a person (MyHeritage id from the GEDCOM FACT)
    place:<Parish/Name>  a gazetteer place
    plac:<raw string>    one place string as written in the tree

The file is private (data/notes/errata.toml); examples/errata.example.toml shows the
format. Fields a fix can change on citation rows: page, row, farm,
series, vol, years, parish, place_id. Person facts (dates, names) are
keyed the same way but not yet applied anywhere.

    [[fix]]
    key = "mh:91482036"
    field = "page"
    was = "35"
    now = "36"
    source = "Riksarkivet image checked"
    date = "2026-11-09"

    [[note]]
    key = "volume:SE/VALA/00221/A I/20"
    text = "MyHeritage reads this as A I 19 (1886-1890); which is right?"
    date = "2026-11-09"
"""
import tomllib
from collections import defaultdict
from pathlib import Path

import textfix

FIELDS = {"page", "row", "farm", "series", "vol", "years", "parish", "place_id"}


def load(path):
    path = Path(path)
    if not path.exists():
        return dict(fix=[], note=[])
    d = tomllib.loads(path.read_text(encoding="utf-8"))
    return dict(fix=d.get("fix", []), note=d.get("note", []))


def keys(r):
    """Every key a citation row answers to."""
    out = []
    if r.get("mh_item"):
        out.append(f"mh:{r['mh_item']}")
    if r.get("image_id") and r.get("image_no"):
        out.append(f"bild:{r['image_id']}_{int(r['image_no']):05d}")
    if r.get("ra_code"):
        out.append(f"volume:{r['ra_code']}")
    if r.get("mh_id"):
        out.append(f"person:{r['mh_id']}")
    if r.get("place_id"):
        out.append(f"place:{r['place_id']}")
    if r.get("event_place"):
        out.append(f"plac:{r['event_place']}")
    return out


def apply(rows, errata):
    """Apply fixes and attach notes in place. Returns a status list
    [(entry, status, n_rows)] for the report."""
    by_key = defaultdict(list)
    for r in rows:
        for k in keys(r):
            by_key[textfix.fix(k)].append(r)
    report = []
    for e in errata["fix"]:
        hits = by_key.get(textfix.fix(e.get("key", "")), [])
        f = e.get("field")
        if f not in FIELDS:
            report.append((e, f"bad field {f!r}", 0))
            continue
        if not hits:
            report.append((e, "orphan", 0))
            continue
        was, now = str(e.get("was", "")), str(e.get("now", ""))
        n_applied = n_retired = n_other = 0
        for r in hits:
            cur = str(r.get(f) or "")
            if cur == was:
                r[f] = now
                r.setdefault("errata", []).append(f"{f}: {was} → {now} ({e.get('source', '')})")
                n_applied += 1
            elif cur == now:
                n_retired += 1
            else:
                n_other += 1
        status = ("applied" if n_applied else "retired" if n_retired and not n_other
                  else "conflict")
        report.append((e, status, len(hits)))
    for e in errata["note"]:
        hits = by_key.get(textfix.fix(e.get("key", "")), [])
        for r in hits:
            r.setdefault("notes", []).append(e.get("text", ""))
        report.append((e, "attached" if hits else "orphan", len(hits)))
    return report


def write_report(path, report):
    lines = ["# Errata status (generated; private)", ""]
    for status in ("conflict", "orphan", "retired", "applied", "attached"):
        part = [x for x in report if x[1] == status or (status == "conflict" and x[1].startswith("bad"))]
        if not part:
            continue
        lines += [f"## {status} ({len(part)})", ""]
        for e, s, n in part:
            what = (f"{e.get('field')}: {e.get('was')} → {e.get('now')}" if "field" in e
                    else e.get("text", ""))
            lines.append(f"- `{e.get('key')}` {what} [{n} rows] {e.get('date', '')}")
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
