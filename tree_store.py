"""
A small, editable store (SQLite) for both halves of the record, the family
tree and the genetics, with readable provenance, that exports again.

Family tree: imported from GEDCOM, edited here, exported as GEDCOM.
Genetics, with the same standing: testers, DNA matches (optionally linked
to a tree person), shared totals, segments, and the phased grandparent
painting; imported from the pipeline's outputs, exported as CSV (and DNA
Painter backups via dnapainter_export).

    python3 tree_store.py import data/tree.ged "MyHeritage export 2026-11-09"
    python3 tree_store.py export data/tree_out.ged [--places]   # --places: MAP/LATI/LONG, _QID
    python3 tree_store.py import-tree            # the configured GEDCOM replaces the tree (edits kept)
    python3 tree_store.py import-places [label]   # gazetteer -> place table, event.place_id
    python3 tree_store.py import-genetics "pipeline 2026-11-09"
    python3 tree_store.py export-genetics data/genetics_out
    python3 tree_store.py notes          # the provenance notes, readable
    python3 tree_store.py rebuild data/tree.ged "label"   # from GEDCOM + pipeline + tree_edits.json, in place
    python3 tree_store.py stats

Not an assertion log: one current value per thing, editable in place. Every
row has an `origin` ("import:<label>" or "edit:<who>"); edits and re-import
conflicts are written to table `change` and `tree_notes.md`. Modelled:
people, families, events, sources, citations; the rest is kept verbatim as
GEDCOM subtrees. The database (in private `data/`, not versioned) is
rebuilt from the GEDCOM, the pipeline outputs and `tree_edits.json`.
`event.place` keeps the imported text; `event.place_id` links the `place`
table (place_store.py). How it works: docs/records.md, "The tree store".
Sketch: dates are kept as written; one NAME per person is modelled.
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import gedcom_io

EVENT_TAGS = {"BIRT", "CHR", "BAPM", "DEAT", "BURI", "CREM", "MARR", "DIV", "ENGA", "RESI", "OCCU",
              "EDUC", "EVEN", "EMIG", "IMMI", "CENS", "PROB", "WILL", "GRAD", "RETI", "CONF", "NATU",
              "RELI", "TITL", "DSCR", "NATI", "ADOP", "_MILT", "FACT"}

SCHEMA = """
create table if not exists record (id text primary key, kind text, xref text, origin text, updated text);
create table if not exists person (id text primary key, given text, surname text, sex text,
    married text, name_extra text, origin text);
create table if not exists family (id text primary key, husb text, wife text, origin text);
create table if not exists child (family text, child text, pedi text, origin text,
    primary key (family, child));
create table if not exists event (n integer primary key, owner text, tag text, type text, date text,
    place text, value text, extra text, origin text);
create table if not exists source (id text primary key, title text, author text, text_ text,
    extra text, origin text);
create table if not exists citation (n integer primary key, owner text, event integer, source text,
    page text, extra text, origin text);
create table if not exists verbatim (n integer primary key, owner text, pos integer, tree text, origin text);
create table if not exists change (n integer primary key, at text, who text, what text, why text);
create table if not exists kit (id text primary key, person text, vendor text, label text, origin text);
create table if not exists dna_match (id text primary key, vendor text, vendor_key text, name text,
    person text, linked_by text, origin text);
create table if not exists shared (kit text, match text, total_cM real, placement text, agreement real,
    source text, origin text, primary key (kit, match));
create table if not exists segment (n integer primary key, kit text, match text, chrom text, start integer,
    end_ integer, cM real, parent text, grandparent text, lineage text, reason text, source text, origin text);
create table if not exists painting (n integer primary key, kit text, chrom text, start integer, end_ integer,
    parent text, lineage text, snps integer, corrected_from text, origin text);
create table if not exists place (id text primary key, name text, kind text, parent text, parish text,
    qid text, archive text, valid_from integer, valid_to integer, lat real, lon real, geo_level text,
    geo_source text, variants text, evidence text, origin text);
"""
# columns added after the first release: (table, column, type)
MIGRATIONS = [("event", "place_id", "text"), ("event", "place_how", "text")]


def _sub(node, tag):
    return next((s for s in node["sub"] if s["tag"] == tag), None)


def _val(node, tag):
    s = _sub(node, tag)
    return s["value"] if s else ""


def _strip(node, tags):
    return [s for s in node["sub"] if s["tag"] not in tags]


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)
        for table, col, typ in MIGRATIONS:
            if col not in [c[1] for c in self.db.execute(f"pragma table_info({table})")]:
                self.db.execute(f"alter table {table} add column {col} {typ}")

    # -- edits on disk: the database can be rebuilt, the edits can't ---------
    EDIT_TABLES = ("person", "family", "child", "event", "source", "citation", "verbatim", "dna_match", "shared", "segment", "painting", "place")

    def dump_edits(self):
        """Write every edited row (origin edit:...) to tree_edits.json next to
        the database: small, readable, versioned; replayed by load_edits."""
        out = {}
        for t in self.EDIT_TABLES:
            cur = self.db.execute(f"select * from {t} where origin like 'edit:%'")
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            if rows:
                out[t] = rows
        self.path.with_name("tree_edits.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    def load_edits(self):
        f = self.path.with_name("tree_edits.json")
        if not f.exists():
            return 0
        n, event_map = 0, {}
        data = json.loads(f.read_text(encoding="utf-8"))
        # events first (citations point at them); row numbers are reassigned,
        # since a newer import may have used the old ones
        for t in sorted(data, key=lambda t: t != "event"):
            for r in data[t]:
                r = dict(r)
                old_n = r.pop("n", None)
                if t == "citation" and r.get("event") is not None:
                    r["event"] = event_map.get(r["event"], r["event"])
                cols = list(r)
                cur = self.db.execute(f"insert or replace into {t} ({', '.join(cols)}) values "
                                      f"({', '.join('?' * len(cols))})", [r[c] for c in cols])
                if t == "event":
                    event_map[old_n] = cur.lastrowid
                n += 1
        self.db.commit()
        return n

    # -- notes --------------------------------------------------------------
    TREE_TABLES = ("record", "person", "family", "child", "event", "source", "citation", "verbatim")

    def import_tree(self, path, label, **options):
        """The tree replaced by a GEDCOM, in place: every tree row cleared
        (people who left the tree go too), the GEDCOM imported, the edits
        replayed from tree_edits.json. The pipeline's tables, the genetics
        and the places stay (the store and places steps re-link them).
        Refuses if the database holds edits tree_edits.json lacks."""
        f = self.path.with_name("tree_edits.json")
        saved = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        for t in self.EDIT_TABLES:
            n = self.db.execute(f"select count(*) from {t} where origin like 'edit:%'").fetchone()[0]
            if n > len(saved.get(t, [])):
                raise RuntimeError(f"{t}: {n} edited rows in the store, {len(saved.get(t, []))} in "
                                   f"{f.name}; run dump_edits before replacing the tree")
        for t in self.TREE_TABLES:
            self.db.execute(f"delete from {t}")
        for t in set(self.EDIT_TABLES) - set(self.TREE_TABLES):
            self.db.execute(f"delete from {t} where origin like 'edit:%'")    # replayed below
        stats = self.import_gedcom(path, label, **options)
        stats["edits_replayed"] = self.load_edits()
        self.db.commit()
        return stats

    def note(self, who, what, why=""):
        at = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.db.execute("insert into change (at, who, what, why) values (?,?,?,?)", (at, who, what, why))
        self.db.commit()
        if who != "import":
            self.dump_edits()
        with open(self.path.with_name("tree_notes.md"), "a", encoding="utf-8") as f:
            f.write(f"- {at} · {who}: {what}" + (f" — {why}" if why else "") + "\n")

    # -- import -------------------------------------------------------------
    def _id(self, r):
        """Stable id: MyHeritage ID when present, else the xref."""
        rin = next((s["value"] for s in r["sub"] if s["tag"] in ("RIN", "FACT")
                    and s["value"].startswith("MH:")), None)
        return rin or r["xref"]

    def _edited(self, table, key, keycol="id"):
        row = self.db.execute(f"select origin from {table} where {keycol}=?", (key,)).fetchone()
        return row and row[0].startswith("edit:")

    def import_gedcom(self, path, label, keep_unlinked=False, root=None):
        """Unlinked people are left out by default (gedcom_io.linked); ones
        an earlier import wrote stay until a rebuild."""
        recs = gedcom_io.parse(path, keep_unlinked=True)
        unlinked = []
        if not keep_unlinked:
            recs, unlinked = gedcom_io.linked(recs, root)
        origin = f"import:{label}"
        ids = {r["xref"]: self._id(r) for r in recs if r["xref"]}
        stats = dict(people=0, families=0, sources=0, kept_edits=0, unlinked_left_out=len(unlinked))
        cur = self.db.cursor()
        for r in recs:
            if not r["xref"]:
                continue                      # HEAD, TRLR: written fresh on export
            rid = ids[r["xref"]]
            cur.execute("insert or replace into record values (?,?,?,?,?)",
                        (rid, r["tag"], r["xref"], origin, datetime.now().isoformat(timespec="seconds")))
            if r["tag"] == "INDI":
                stats["people"] += 1
                self._import_person(cur, r, rid, ids, origin, stats)
            elif r["tag"] == "FAM":
                stats["families"] += 1
                self._import_family(cur, r, rid, ids, origin, stats)
            elif r["tag"] == "SOUR":
                stats["sources"] += 1
                if not self._edited("source", rid):
                    cur.execute("insert or replace into source values (?,?,?,?,?,?)",
                                (rid, _val(r, "TITL"), _val(r, "AUTH"), _val(r, "TEXT"),
                                 json.dumps(_strip(r, {"TITL", "AUTH", "TEXT"}), ensure_ascii=False), origin))
            else:
                self._replace_verbatim(cur, rid, r["sub"], origin)
        # pedigree links written on the child's FAMC (adopted, foster): make
        # sure the child row exists and carries the type
        for r in recs:
            if r["tag"] != "INDI":
                continue
            for f in r["sub"]:
                if f["tag"] == "FAMC":
                    pedi = _val(f, "PEDI")
                    fam, kid = ids.get(f["value"], f["value"]), ids[r["xref"]]
                    cur.execute("insert or ignore into child values (?,?,?,?)", (fam, kid, pedi or None, origin))
                    if pedi:
                        cur.execute("update child set pedi=? where family=? and child=?", (pedi, fam, kid))
        self.db.commit()
        self.note("import", f"imported {Path(path).name} as '{label}': {stats['people']} people, "
                            f"{stats['families']} families, {stats['sources']} sources; "
                            f"{stats['kept_edits']} edited rows kept")
        return stats

    def _replace_verbatim(self, cur, owner, subs, origin):
        cur.execute("delete from verbatim where owner=? and origin like 'import:%'", (owner,))
        for k, s in enumerate(subs):
            cur.execute("insert into verbatim (owner, pos, tree, origin) values (?,?,?,?)",
                        (owner, k, json.dumps(s, ensure_ascii=False), origin))

    def _import_person(self, cur, r, pid, ids, origin, stats):
        names = [s for s in r["sub"] if s["tag"] == "NAME"]
        if self._edited("person", pid):
            stats["kept_edits"] += 1
        else:
            n = names[0] if names else {"value": "", "sub": []}
            given, _, rest = n["value"].partition("/")
            married = [s["value"] for s in n["sub"] if s["tag"] == "_MARNM"]
            cur.execute("insert or replace into person values (?,?,?,?,?,?,?)",
                        (pid, given.strip(), rest.split("/")[0].strip(), _val(r, "SEX"),
                         json.dumps(married, ensure_ascii=False),
                         json.dumps([s for s in n["sub"] if s["tag"] not in ("GIVN", "SURN", "_MARNM")]
                                    + [{"tag": "NAME+", "value": x["value"], "sub": x["sub"], "xref": None}
                                       for x in names[1:]], ensure_ascii=False), origin))
        # events and citations from an import are replaced; edited ones stay
        cur.execute("delete from citation where owner=? and origin like 'import:%'", (pid,))
        cur.execute("delete from event where owner=? and origin like 'import:%'", (pid,))
        rest = []
        for s in r["sub"]:
            if s["tag"] in ("NAME", "SEX", "FAMC", "FAMS"):
                continue
            if s["tag"] == "SOUR":
                cur.execute("insert into citation (owner, event, source, page, extra, origin) values (?,?,?,?,?,?)",
                            (pid, None, ids.get(s["value"], s["value"]), _val(s, "PAGE"),
                             json.dumps(_strip(s, {"PAGE"}), ensure_ascii=False), origin))
            elif s["tag"] in EVENT_TAGS:
                cur.execute("insert into event (owner, tag, type, date, place, value, extra, origin) "
                            "values (?,?,?,?,?,?,?,?)",
                            (pid, s["tag"], _val(s, "TYPE"), _val(s, "DATE"), _val(s, "PLAC"), s["value"],
                             json.dumps(_strip(s, {"TYPE", "DATE", "PLAC"}), ensure_ascii=False), origin))
            else:
                rest.append(s)
        self._replace_verbatim(cur, pid, rest, origin)

    def _import_family(self, cur, r, fid, ids, origin, stats):
        if self._edited("family", fid):
            stats["kept_edits"] += 1
        else:
            cur.execute("insert or replace into family values (?,?,?,?)",
                        (fid, ids.get(_val(r, "HUSB")) or None, ids.get(_val(r, "WIFE")) or None, origin))
        cur.execute("delete from child where family=? and origin like 'import:%'", (fid,))
        for s in r["sub"]:
            if s["tag"] == "CHIL":
                cur.execute("insert or ignore into child values (?,?,?,?)",
                            (fid, ids.get(s["value"], s["value"]), _val(s, "PEDI") or None, origin))
        cur.execute("delete from event where owner=? and origin like 'import:%'", (fid,))
        rest = []
        for s in r["sub"]:
            if s["tag"] in ("HUSB", "WIFE", "CHIL"):
                continue
            if s["tag"] in EVENT_TAGS:
                cur.execute("insert into event (owner, tag, type, date, place, value, extra, origin) "
                            "values (?,?,?,?,?,?,?,?)",
                            (fid, s["tag"], _val(s, "TYPE"), _val(s, "DATE"), _val(s, "PLAC"), s["value"],
                             json.dumps(_strip(s, {"TYPE", "DATE", "PLAC"}), ensure_ascii=False), origin))
            else:
                rest.append(s)
        self._replace_verbatim(cur, fid, rest, origin)

    # -- genetics -------------------------------------------------------------
    def import_genetics(self, cfg, label):
        """From the pipeline's outputs: testers from family.toml (people with
        an `mh`), matches and totals from placed_matches.csv, segments from
        placed_segments.csv, the painting (with its current corrections), and match ->
        person links from [[identity]]. Imported rows are replaced; edited
        rows (origin edit:...) are kept."""
        import pandas as pd
        import match_placement as mp
        import outputs
        D = cfg["data_dir"]
        origin = f"import:{label}"
        # the pipeline's tables, read before this connection starts writing
        # (outputs.read opens its own connection to the same database)
        placed = outputs.read(D, "placed_matches.csv")
        segs = outputs.read(D, "placed_segments.csv", dtype={"chrom": str})
        paint = mp.load_painting(D)
        cur = self.db.cursor()
        for t in ("kit", "dna_match", "shared", "segment", "painting"):
            cur.execute(f"delete from {t} where origin like 'import:%'")
        kits = {}
        for key, p in cfg["people"].items():
            for vendor in ("FTDNA", "MyHeritage"):
                kid = f"{key}:{vendor}"
                kits[(key, vendor)] = kid
                cur.execute("insert or ignore into kit values (?,?,?,?,?)",
                            (kid, p.get("mh"), vendor, p.get("name", key), origin))
        ident = {gedcom_io._norm(x["match"]): (x["tree"], x.get("by", "")) for x in cfg.get("identity", [])}
        for r in placed.drop_duplicates(["platform", "match_key"]).itertuples():
            mid = f"{r.platform}:{r.match_key}"
            person, by = ident.get(gedcom_io._norm(str(r.match)), (None, ""))
            cur.execute("insert or ignore into dna_match values (?,?,?,?,?,?,?)",
                        (mid, r.platform, r.match_key, r.match, person, by or None, origin))
        for r in placed.itertuples():
            cur.execute("insert or ignore into shared values (?,?,?,?,?,?,?)",
                        (kits.get((r.subject, r.platform)), f"{r.platform}:{r.match_key}", r.shared_cM,
                         r.placement, r.agreement, "placed_matches.csv", origin))
        # matches seen only in AutoCluster runs (no segment export): their totals
        import icw_io
        for x in cfg.get("icw", []):
            if x["kind"] != "autocluster":
                continue
            nodes, _ = icw_io.autocluster_matrix(D / x["file"], x["subject"], x.get("platform", "MyHeritage"))
            for r in nodes.itertuples():
                mid = f"{r.platform}:{r.match_key}"
                person, by = ident.get(gedcom_io._norm(str(r.match)), (None, ""))
                cur.execute("insert or ignore into dna_match values (?,?,?,?,?,?,?)",
                            (mid, r.platform, r.match_key, r.match, person, by or None, origin))
                cur.execute("insert or ignore into shared values (?,?,?,?,?,?,?)",
                            (kits.get((r.subject, r.platform)), mid, r.cM, None, None, Path(x["file"]).name, origin))
        for r in segs.itertuples():
            cur.execute("insert into segment (kit, match, chrom, start, end_, cM, parent, grandparent, lineage, "
                        "reason, source, origin) values (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (kits.get((r.subject, r.platform)), f"{r.platform}:{r.match_key}", r.chrom,
                         int(r.start), int(r.end), float(r.cM),
                         r.parent if isinstance(r.parent, str) else None,
                         r.grandparent if isinstance(r.grandparent, str) else None, None,
                         r.parent_reason if isinstance(r.parent_reason, str) else None, r.source, origin))
        for r in paint.itertuples():
            cur.execute("insert into painting (kit, chrom, start, end_, parent, lineage, snps, corrected_from, origin) "
                        "values (?,?,?,?,?,?,?,?,?)",
                        (f"{r.subject}:raw", r.chrom, int(r.start), int(r.end), r.parent, r.lineage, int(r.snps),
                         getattr(r, "corrected_from", None) if isinstance(getattr(r, "corrected_from", None), str)
                         and getattr(r, "corrected_from") else None, origin))
        self.db.commit()
        n = {t: self.db.execute(f"select count(*) from {t}").fetchone()[0]
             for t in ("dna_match", "shared", "segment", "painting")}
        linked = self.db.execute("select count(*) from dna_match where person is not null").fetchone()[0]
        self.note("import", f"genetics from the pipeline as '{label}': {n['dna_match']} matches "
                            f"({linked} linked to tree people), {n['shared']} tester-match totals, "
                            f"{n['segment']} segments, {n['painting']} painting blocks")
        return n | {"linked": linked}

    def link_match(self, match_id, person, who, why):
        old = self.db.execute("select person from dna_match where id=?", (match_id,)).fetchone()
        self.db.execute("update dna_match set person=?, linked_by=?, origin=? where id=?",
                        (person, who, f"edit:{who}", match_id))
        self.db.commit()
        self.note(who, f"DNA match {match_id} -> tree person {person} (was {old[0] if old else None})", why)

    def set_segment_lineage(self, n, lineage, who, why):
        old = self.db.execute("select kit, match, chrom, start, end_, grandparent, lineage from segment where n=?",
                              (n,)).fetchone()
        self.db.execute("update segment set lineage=?, origin=? where n=?", (lineage, f"edit:{who}", n))
        self.db.commit()
        self.note(who, f"segment {old[0]} x {old[1]} chr{old[2]}:{old[3]}-{old[4]}: lineage {lineage} "
                       f"(placement said {old[5]}, was {old[6]})", why)

    def export_genetics(self, outdir):
        import pandas as pd
        out = Path(outdir)
        out.mkdir(parents=True, exist_ok=True)
        for t in ("kit", "dna_match", "shared", "segment", "painting"):
            pd.read_sql(f"select * from {t}", self.db).to_csv(out / f"{t}.csv", index=False)
        return {t: self.db.execute(f"select count(*) from {t}").fetchone()[0]
                for t in ("kit", "dna_match", "shared", "segment", "painting")}

    # -- edits --------------------------------------------------------------
    def set_person(self, pid, who, why, **fields):
        old = self.db.execute("select given, surname, sex from person where id=?", (pid,)).fetchone()
        sets = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"update person set {sets}, origin=? where id=?", (*fields.values(), f"edit:{who}", pid))
        self.db.commit()
        self.note(who, f"{pid}: set {fields} (was {old})", why)

    def add_event(self, owner, tag, who, why, type="", date="", place="", value="", source=None, page=""):
        cur = self.db.execute("insert into event (owner, tag, type, date, place, value, extra, origin) "
                              "values (?,?,?,?,?,?,?,?)",
                              (owner, tag, type, date, place, value, "[]", f"edit:{who}"))
        if source:
            self.db.execute("insert into citation (owner, event, source, page, extra, origin) values (?,?,?,?,?,?)",
                            (owner, cur.lastrowid, source, page, "[]", f"edit:{who}"))
        self.db.commit()
        self.note(who, f"{owner}: added {tag} {type} {date} {place} {value}".strip(), why)
        return cur.lastrowid

    def set_event(self, n, who, why, **fields):
        old = self.db.execute("select owner, tag, date, place from event where n=?", (n,)).fetchone()
        sets = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"update event set {sets}, origin=? where n=?", (*fields.values(), f"edit:{who}", n))
        self.db.commit()
        self.note(who, f"{old[0]} {old[1]}: set {fields} (was date {old[2]!r}, place {old[3]!r})", why)

    def add_source(self, sid, title, who, why, author="", text=""):
        self.db.execute("insert or replace into source values (?,?,?,?,?,?)",
                        (sid, title, author, text, "[]", f"edit:{who}"))
        self.db.commit()
        self.note(who, f"source {sid}: {title}", why)

    def events(self, owner, tag=None):
        q = "select n, tag, type, date, place, value, origin from event where owner=?"
        return self.db.execute(q + (" and tag=?" if tag else ""), (owner, tag) if tag else (owner,)).fetchall()

    # -- export -------------------------------------------------------------
    def export_gedcom(self, out, dedupe_citations=True, place_coords=False):
        """place_coords: under each PLAC also write MAP/LATI/LONG (and _QID
        for a parish) from the linked place; the PLAC text stays as imported."""
        db = self.db
        xref = {}
        coords = {}
        if place_coords:
            for pid, lat, lon, qid in db.execute("select id, lat, lon, qid from place"):
                coords[pid] = (lat, lon, qid)

        def emit_place(level, place, place_id):
            emit(level, "PLAC", place)
            c = coords.get(place_id) if place_id else None
            if c and c[0] is not None:
                emit(level + 1, "MAP")
                emit(level + 2, "LATI", f"{'N' if c[0] >= 0 else 'S'}{abs(c[0]):.5f}")
                emit(level + 2, "LONG", f"{'E' if c[1] >= 0 else 'W'}{abs(c[1]):.5f}")
            if c and c[2]:
                emit(level + 1, "_QID", c[2])

        def x(i, prefix):
            if i not in xref:
                row = db.execute("select xref from record where id=?", (i,)).fetchone()
                xref[i] = row[0] if row and row[0] else f"@{prefix}{len(xref) + 1}@"
            return xref[i]

        L = ["0 HEAD", "1 SOUR synthetic_genealogy", "2 NAME tree_store.py", "1 GEDC", "2 VERS 5.5.1",
             "2 FORM LINEAGE-LINKED", "1 CHAR UTF-8", f"1 DATE {datetime.now():%d %b %Y}".upper()]

        def emit(level, tag, value="", ref=None):
            head = f"{level} {ref + ' ' if ref else ''}{tag}"
            parts = str(value).split("\n") if value != "" else [""]
            first = True
            for part in parts:
                chunks = [part[i:i + 200] for i in range(0, len(part), 200)] or [""]   # whole characters
                for k, c in enumerate(chunks):
                    if first:
                        L.append(f"{head} {c}".rstrip() if c else head)
                        first = False
                    else:
                        L.append(f"{level + 1} {'CONC' if k else 'CONT'} {c}".rstrip())

        def tree(level, nodes):
            for n in nodes:
                tag = "NAME" if n["tag"] == "NAME+" else n["tag"]
                emit(level, tag, n["value"])
                tree(level + 1, n["sub"])

        fams_of, famc_of = {}, {}
        for fid, h, w in db.execute("select id, husb, wife from family"):
            for p in (h, w):
                if p:
                    fams_of.setdefault(p, []).append(fid)
        for fid, c, pedi in db.execute("select family, child, pedi from child"):
            famc_of.setdefault(c, []).append((fid, pedi))
        dropped = 0
        for pid, given, surname, sex, married, name_extra in db.execute(
                "select id, given, surname, sex, married, name_extra from person order by rowid"):
            emit(0, "INDI", ref=x(pid, "I"))
            emit(1, "NAME", f"{given} /{surname}/".strip())
            if given:
                emit(2, "GIVN", given)
            if surname:
                emit(2, "SURN", surname)
            for m in json.loads(married or "[]"):
                emit(2, "_MARNM", m)
            extra = json.loads(name_extra or "[]")
            tree(2, [n for n in extra if n["tag"] != "NAME+"])
            tree(1, [n for n in extra if n["tag"] == "NAME+"])
            if sex:
                emit(1, "SEX", sex)
            for n, tag, typ, date, place, value, ext, place_id in db.execute(
                    "select n, tag, type, date, place, value, extra, place_id from event where owner=? order by n",
                    (pid,)):
                emit(1, tag, value or "")
                if typ:
                    emit(2, "TYPE", typ)
                if date:
                    emit(2, "DATE", date)
                if place:
                    emit_place(2, place, place_id)
                tree(2, json.loads(ext or "[]"))
                for src, page in db.execute("select source, page from citation where event=?", (n,)):
                    emit(2, "SOUR", x(src, "S"))
                    if page:
                        emit(3, "PAGE", page)
            for _, tr in db.execute("select pos, tree from verbatim where owner=? order by pos", (pid,)):
                tree(1, [json.loads(tr)])
            for mid, vendor, name in db.execute(
                    "select id, vendor, name from dna_match where person=?", (pid,)):
                tot = db.execute("select kit, total_cM from shared where match=? and total_cM is not null",
                                 (mid,)).fetchall()
                emit(1, "EVEN", f"{vendor}: {name}")
                emit(2, "TYPE", "DNA match")
                if tot:
                    emit(2, "NOTE", "; ".join(f"{k.split(':')[0]} {c:.0f} cM" for k, c in tot))
            seen = set()
            for src, page, ext in db.execute(
                    "select source, page, extra from citation where owner=? and event is null order by n", (pid,)):
                if dedupe_citations and (src, page, ext) in seen:
                    dropped += 1
                    continue
                seen.add((src, page, ext))
                emit(1, "SOUR", x(src, "S"))
                if page:
                    emit(2, "PAGE", page)
                tree(2, json.loads(ext or "[]"))
            for fid, pedi in famc_of.get(pid, []):
                emit(1, "FAMC", x(fid, "F"))
                if pedi:
                    emit(2, "PEDI", pedi)
            for fid in fams_of.get(pid, []):
                emit(1, "FAMS", x(fid, "F"))
        for fid, h, w in db.execute("select id, husb, wife from family order by rowid"):
            emit(0, "FAM", ref=x(fid, "F"))
            if h:
                emit(1, "HUSB", x(h, "I"))
            if w:
                emit(1, "WIFE", x(w, "I"))
            for c, pedi in db.execute("select child, pedi from child where family=?", (fid,)):
                emit(1, "CHIL", x(c, "I"))
            for n, tag, typ, date, place, value, ext, place_id in db.execute(
                    "select n, tag, type, date, place, value, extra, place_id from event where owner=? order by n",
                    (fid,)):
                emit(1, tag, value or "")
                for t_, v in (("TYPE", typ), ("DATE", date)):
                    if v:
                        emit(2, t_, v)
                if place:
                    emit_place(2, place, place_id)
                tree(2, json.loads(ext or "[]"))
            for _, tr in db.execute("select pos, tree from verbatim where owner=? order by pos", (fid,)):
                tree(1, [json.loads(tr)])
        for sid, title, author, text, ext in db.execute(
                "select id, title, author, text_, extra from source order by rowid"):
            emit(0, "SOUR", ref=x(sid, "S"))
            if author:
                emit(1, "AUTH", author)
            if title:
                emit(1, "TITL", title)
            if text:
                emit(1, "TEXT", text)
            tree(1, json.loads(ext or "[]"))
        for rid, kind in db.execute("select id, kind from record where kind not in ('INDI','FAM','SOUR')"):
            emit(0, kind, ref=x(rid, "X"))
            for _, tr in db.execute("select pos, tree from verbatim where owner=? order by pos", (rid,)):
                tree(1, [json.loads(tr)])
        L.append("0 TRLR")
        Path(out).write_text("\n".join(L) + "\n", encoding="utf-8")
        return dict(lines=len(L), citations_dropped=dropped)

    def stats(self):
        q = lambda s: self.db.execute(s).fetchone()[0]
        return {t: q(f"select count(*) from {t}") for t in
                ("person", "family", "child", "event", "source", "citation", "verbatim", "change",
                 "kit", "dna_match", "shared", "segment", "painting", "place")} | {
            "events with a place": q("select count(*) from event where place <> ''"),
            "events linked to a place": q("select count(*) from event where place_id is not null"),
            "edited rows": q("select count(*) from event where origin like 'edit:%'")
                           + q("select count(*) from person where origin like 'edit:%'")}


def default_store():
    import config
    cfg = config.load()
    return Store(cfg["data_dir"] / "tree.sqlite")


if __name__ == "__main__":
    cmd, *a = sys.argv[1:] or ["stats"]
    s = default_store()
    import config
    if cmd == "import":
        print(s.import_gedcom(a[0], a[1] if len(a) > 1 else Path(a[0]).name,
                              **gedcom_io.options(config.load())))
    elif cmd == "export":
        print(s.export_gedcom(a[0], place_coords="--places" in a))
    elif cmd == "import-places":
        import place_store
        print(place_store.import_places(s, a[0] if a else "gazetteer"))
    elif cmd == "import-genetics":
        import config
        print(s.import_genetics(config.load(), a[0] if a else "pipeline"))
    elif cmd == "export-genetics":
        print(s.export_genetics(a[0]))
    elif cmd == "import-tree":
        # the configured GEDCOM ([gedcom] file) replaces the tree, edits replayed
        import config
        cfg = config.load()
        ged = config.path(cfg, cfg["gedcom"]["file"])
        r = s.import_tree(ged, Path(ged).name, **gedcom_io.options(cfg))
        s.note("import", f"tree from {Path(ged).name}: {r}")
        print(r)
    elif cmd == "rebuild":
        # tree, genetics and places again from a GEDCOM, the pipeline outputs and
        # tree_edits.json, in place: the pipeline's own tables live in this
        # database too (outputs.py), so it is not deleted
        import config
        print(s.import_tree(a[0], a[1] if len(a) > 1 else Path(a[0]).name,
                            **gedcom_io.options(config.load())))
        print(s.import_genetics(config.load(), "pipeline"))
        import place_store
        print(place_store.import_places(s, "gazetteer"))
    elif cmd == "notes":
        print(s.path.with_name("tree_notes.md").read_text(encoding="utf-8"))
    else:
        print(s.stats())
