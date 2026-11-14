"""
Quick read-only questions to the tree store: who is this, whose child, whose
parent. For a session that needs one fact without reading the store's code.

    python3 store_query.py find "anna andersson"   # matching people, one line each
    python3 store_query.py person "anna andersson" # parents, spouses, children, kits
    python3 store_query.py person MH:I123             # by store id
    python3 store_query.py sql "select count(*) from person"   # anything else, read-only

Names match case- and accent-insensitively and ignoring doubled letters
(Andersson finds Anderson), every word against given name,
surname and married names, so "anna andersson" finds an Anna born
Andersson or married into it. `person` with a name that fits several
people lists them instead. `--db <path>` reads another store; otherwise the
store of `family.toml` (or `FAMILY_CONFIG`). The database is opened
read-only, so nothing here can change it.
"""
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path


def connect(path=None):
    if path is None:
        import config
        path = config.load()["data_dir"] / "tree.sqlite"
    if not Path(path).exists():
        raise SystemExit(f"{path} not found: build it with tree_store.py rebuild")
    db = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)   # as_uri: Windows drive letters, spaces
    db.row_factory = sqlite3.Row
    return db


def _fold(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    return re.sub(r"(\w)\1+", r"\1", s)   # Andersson = Anderson


def _married(row):
    try:
        return json.loads(row["married"] or "[]")
    except ValueError:
        return [row["married"]]


def _year(db, pid, tags):
    for tag in tags:
        r = db.execute("select date from event where owner=? and tag=? and date<>'' order by n limit 1",
                       (pid, tag)).fetchone()
        if r:
            m = re.search(r"\d{4}", r["date"])
            return m.group(0) if m else r["date"]
    return ""


def label(db, pid):
    """'Given Surname (married M) b. 1900 d. 1980 [id]' for one person."""
    if not pid:
        return "(unknown)"
    r = db.execute("select * from person where id=?", (pid,)).fetchone()
    if r is None:
        return f"(missing {pid})"
    name = " ".join(x for x in (r["given"], r["surname"]) if x) or "(no name)"
    m = _married(r)
    if m:
        name += f" (married {', '.join(m)})"
    b, d = _year(db, pid, ("BIRT", "CHR", "BAPM")), _year(db, pid, ("DEAT", "BURI"))
    life = " ".join(x for x in (b and f"b. {b}", d and f"d. {d}") if x)
    return f"{name}{' ' + life if life else ''} [{pid}]"


def find(db, query):
    """Ids of the people whose names contain every word of `query`."""
    words = _fold(query).split()
    hits = []
    for r in db.execute("select id, given, surname, married from person order by id"):
        hay = _fold(" ".join([r["given"] or "", r["surname"] or "", *_married(r)]))
        if all(w in hay for w in words):
            hits.append(r["id"])
    return hits


def resolve(db, who):
    """A store id as given, else the people the name finds."""
    if db.execute("select 1 from person where id=?", (who,)).fetchone():
        return [who]
    return find(db, who)


def relatives(db, pid):
    """Parents (per family, with pedigree type), and spouses with their children."""
    parents = [dict(family=r["id"], father=r["husb"], mother=r["wife"], pedi=r["pedi"] or "")
               for r in db.execute("select f.id, f.husb, f.wife, c.pedi from child c "
                                   "join family f on f.id=c.family where c.child=?", (pid,))]
    unions = []
    for f in db.execute("select * from family where husb=? or wife=?", (pid, pid)):
        kids = [r["child"] for r in db.execute("select child from child where family=?", (f["id"],))]
        unions.append(dict(family=f["id"], spouse=f["wife"] if f["husb"] == pid else f["husb"],
                           children=kids))
    return dict(parents=parents, unions=unions)


def describe(db, pid):
    lines = [label(db, pid)]
    rel = relatives(db, pid)
    for p in rel["parents"] or [dict(father=None, mother=None, pedi="", family="")]:
        tag = f" ({p['pedi']})" if p["pedi"] and p["pedi"] != "birth" else ""
        lines.append(f"  father{tag}: {label(db, p['father'])}")
        lines.append(f"  mother{tag}: {label(db, p['mother'])}")
    for u in rel["unions"]:
        lines.append(f"  spouse: {label(db, u['spouse']) if u['spouse'] else '(none recorded)'}")
        lines += [f"    child: {label(db, c)}" for c in u["children"]]
    for k in db.execute("select id, vendor, label from kit where person=?", (pid,)):
        lines.append(f"  kit: {k['vendor']} {k['label'] or k['id']}")
    return "\n".join(lines)


def main(argv):
    db_path = None
    if "--db" in argv:
        i = argv.index("--db")
        db_path, argv = argv[i + 1], argv[:i] + argv[i + 2:]
    if len(argv) < 2 or argv[0] not in ("find", "person", "sql"):
        print(__doc__.strip())
        return 2
    cmd, arg = argv[0], " ".join(argv[1:])
    db = connect(db_path)
    if cmd == "sql":
        cur = db.execute(arg)
        print("\t".join(d[0] for d in cur.description or []))
        for r in cur:
            print("\t".join("" if v is None else str(v) for v in r))
        return 0
    ids = resolve(db, arg)
    if not ids:
        print(f"no one matches {arg!r}")
        return 1
    if cmd == "find" or len(ids) > 1:
        if cmd == "person":
            print(f"{len(ids)} people match {arg!r}; ask again by id:")
        for pid in ids:
            print(label(db, pid))
        return 0
    print(describe(db, ids[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
