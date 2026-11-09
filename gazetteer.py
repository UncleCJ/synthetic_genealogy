"""
A curated gazetteer: the places this research touches, as stable entities
with their spelling variants, kept apart from the tree that cites them.

MyHeritage stays the master for people and events. Its place strings are
never edited here; they are *resolved* to gazetteer entries on every run,
so a fresh export flows through the same mapping and gives the same
output, and anything new shows up as a to-do instead of silently.

Files (geography is public knowledge, so the gazetteer is public):

    gazetteer/parishes.toml   one table per parish: archive code, Wikidata
                              item, coordinates, aliases
    gazetteer/places.toml     villages (by), farms and crofts, keyed
                              "Parish/Name": variants, within, kind, ...
    gazetteer/cache/          Riksarkivet and Wikidata answers (public)

and, private (it is keyed by the family's own place strings, which can
include living people's addresses):

    data/plac_map.toml        explicit overrides: a raw place string ->
                              a place id, for what the rules get wrong

Editing rules: `build` only adds entries and fills empty fields; it never
overwrites or deletes. Set `checked = true` on an entry once it has been
looked at. Variants are matched after `fold()`, which evens out case,
w/v, q/k, ph/f, th/t, dt/t, the abbreviation gd = gård
and doubled letters; anything looser
(Kjellerö ~ Källerö, Mjerhult ~ Mjärhult) is proposed in
data/gazetteer_todo.md for a person to accept by adding a variant.

Written names are split into levels by parse(): "Roten Ingarp Rote
Swenshult" becomes the farm Svenshult `within` "Ingarps rote", and
"Swenshult Torpet Swenstorp" the croft Svenstorp within Svenshult. Each
entry is named in its least redundant, modern spelling (modern()); every
written form is kept as a variant, so it resolves on the next export.

Only places of record are added automatically: those in household-
examination citations, and parts of PLAC strings before 1950 that hold
no digits and no street words (gatan, vägen, kvarteret). Modern
addresses stay out of the public file.

Sketch status: run on one tree. Place ids are "Parish/Name" and stay
stable as long as the entry is not renamed; rename by adding the old
name as a variant instead.

    python gazetteer.py build              # seed/extend from the tree
    python gazetteer.py build --wikidata   # also fetch missing coordinates
    python gazetteer.py show Hagelstorp    # entries and what resolves to them
"""
import difflib
import re
import sys
import tomllib
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import textfix

ROOT = Path(__file__).parent / "gazetteer"
CACHE = ROOT / "cache"


# -- folding and TOML ---------------------------------------------------------------

def fold(name):
    """Comparison key for place names: spelling noise removed, å/ä/ö kept."""
    s = textfix.fix(name or "").lower().strip().rstrip(".,")
    s = re.sub(r"[\s_-]+", " ", s)
    for a, b in (("w", "v"), ("q", "k"), ("ph", "f"), ("th", "t"), ("dt", "t"),
                 ("ck", "k"), ("z", "s")):
        s = s.replace(a, b)
    s = re.sub(r"(?<=\w)gd\b|(?<=\w)g:d\b", "gård", s)      # "Bultagd" = Bultagård
    return re.sub(r"([a-zåäö])\1+", r"\1", s)


def ascii_slug(s):
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-z0-9]+", "-", s.encode("ascii", "ignore").decode().lower()).strip("-")


_C = "b-df-hj-np-tv-zß"         # consonants, for genitive s


def modern(name):
    """The display spelling of a place name: the least redundant, modern
    form ("Swenshult" -> "Svenshult", "Ulfvestorp" -> "Ulvestorp",
    "Qvatarp" -> "Kvatarp"). The written forms stay as variants."""
    s = textfix.fix(name or "").strip(" .,;:")
    for a, b in (("W", "V"), ("w", "v"), ("fv", "v"), ("Qv", "Kv"), ("Qu", "Kv"),
                 ("qv", "kv"), ("qu", "kv"), ("ph", "f")):
        s = s.replace(a, b)
    s = re.sub(r"(?<=\w)gd\b\.?", "gård", s)                  # Bultagd -> Bultagård
    return s[:1].upper() + s[1:]


def rote_name(x):
    """'Ingarps', 'Ingarp' -> 'Ingarps rote'; 'Källerö' -> 'Källerö rote'."""
    base = re.sub(rf"(?<=[{_C}])s$", "", modern(x))
    return base + ("s" if re.search(rf"[{_C}]$", base) else "") + " rote"


# How household-examination books (and MyHeritage's indexers) write a place
# inside a rote (a district of the parish) or a croft under a farm.
_ROTE = [
    re.compile(r"^Roten\s+(?P<rote>.+?)\s+Rote\.?(?:\s+(?P<rest>.+))?$", re.I),  # Roten X Rote [Y]
    re.compile(r"^Roten\s+(?P<rote>\S+)(?:\s+(?P<rest>.+))?$", re.I),              # Roten X [Y]
    re.compile(r"^(?P<rote>\S+)\s+rote\.?(?:\s*\((?P<no>\w+)\))?$", re.I),     # X rote (femte)
    re.compile(r"^(?P<rest>.+?)\s+(?P<rote>\S+)\s+Rote\.?$", re.I),               # Y X Rote
]
_TORP = re.compile(r"^(?P<farm>.+?)\s+(?:Torpet|Torp|T\.)\s+(?P<croft>.+)$")
_TORP_ALONE = re.compile(r"^(?:Torpet|Torp|T\.)\s+(?P<croft>.+)$")


def parse(raw):
    """A written place name -> [(display name, kind)], outermost first:
    'Roten Ingarp Rote Swenshult' -> [('Ingarps rote', 'rote'), ('Svenshult', '')]
    'Swenshult Torpet Swenstorp'  -> [('Svenshult', ''), ('Svenstorp', 'torp')]
    Heuristic: only the rote and torp patterns are taken apart."""
    s = re.sub(r"(?<=[a-zåäö])(?=[A-ZÅÄÖ])", " ", _clean(textfix.fix(raw)))
    for rx in _ROTE:
        m = rx.match(s)
        if m:
            chain = [(rote_name(m["rote"]), "rote")]
            return chain + (parse(m["rest"]) if m.groupdict().get("rest") else [])
    m = _TORP.match(s)
    if m:
        return parse(m["farm"]) + [(modern(m["croft"]), "torp")]
    m = _TORP_ALONE.match(s)
    if m:
        return [(modern(m["croft"]), "torp")]
    return [(modern(s), "")]


def _toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def dump_toml(header, tables, order):
    """Tables {key: {field: value}} as TOML, fields in `order` first, empty
    values left out, keys sorted, so diffs stay small."""
    out = [header.rstrip(), ""]
    for key in sorted(tables, key=lambda k: (fold(k), k)):
        out.append(f"[{_toml_value(key)}]")
        t = tables[key]
        for f in order + sorted(set(t) - set(order)):
            if f in t and t[f] not in ("", None, [], ()):
                out.append(f"{f} = {_toml_value(t[f])}")
        out.append("")
    return "\n".join(out)


def _load(path):
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


PARISH_FIELDS = ["archive", "archive_from", "wikidata", "label", "lat", "lon",
                 "harad", "aliases", "note", "checked"]
PLACE_FIELDS = ["name", "parish", "kind", "within", "variants", "lat", "lon",
                "tora", "note", "checked"]

PARISH_HEADER = """\
# Parishes in the research: archive code (Riksarkivet reference code of the
# parish archive), Wikidata item, coordinates (of the parish or its socken).
# Generated by gazetteer.py build, then curated by hand: a rebuild only fills
# empty fields and adds parishes. `aliases` are other spellings that should
# resolve here ("Källeryds", "Kjelleryd").
"""
PLACE_HEADER = """\
# Villages (by), farms and crofts, keyed "Parish/Name". Generated from
# record citations and pre-1950 place strings, then curated by hand:
#   variants  other spellings of the same place (also MyHeritage's readings)
#   within    the id of the village a farm lies in ("Källeryd/Hagelstorp")
#   kind      by | gård | torp | ... (free text)
#   checked   true once a person has looked at the entry
# A rebuild only adds entries and fills empty fields. Rename by adding the
# old name as a variant, so the id stays stable.
"""


# -- the gazetteer ----------------------------------------------------------------------

class Gazetteer:
    def __init__(self, root=ROOT, plac_map=None):
        self.root = Path(root)
        self.parishes = _load(self.root / "parishes.toml")
        self.places = _load(self.root / "places.toml")
        self.plac_map_path = Path(plac_map) if plac_map else None
        self.plac_map = {textfix.fix(k): v for k, v in
                         _load(self.plac_map_path).items()} if plac_map else {}
        self._index()

    def _index(self):
        self.parish_index = {}
        for name, p in self.parishes.items():
            for n in [name] + list(p.get("aliases", [])):
                self.parish_index[fold(n)] = name
        self.place_index = {}
        for pid, p in self.places.items():
            for n in [p.get("name", pid.split("/", 1)[-1])] + list(p.get("variants", [])):
                self.place_index[(p.get("parish", ""), fold(n))] = pid

    # lookups
    def parish(self, name):
        """Canonical parish name for a spelling, archive genitive included."""
        k = fold(name)
        if k in self.parish_index:
            return self.parish_index[k]
        if k.endswith("s") and k[:-1] in self.parish_index:
            return self.parish_index[k[:-1]]
        return None

    def place(self, parish, name):
        """Place id for a written name: as written (any recorded variant),
        else by its parsed innermost part ('Roten Ingarp Rote Swenshult'
        -> Svenshult)."""
        parish = self.parish(parish) or parish
        hit = self.place_index.get((parish, fold(name)))
        if hit or not name:
            return hit
        return self.place_index.get((parish, fold(parse(name)[-1][0])))

    def resolve(self, parish, name, raw=None):
        """(place id or None, how). An explicit plac_map entry wins."""
        for key in (raw, f"{parish}: {name}"):
            if key and textfix.fix(key) in self.plac_map:
                return self.plac_map[textfix.fix(key)].get("place"), "plac_map"
        pid = self.place(parish, name) if parish and name else None
        return pid, ("gazetteer" if pid else "")

    def unique_place(self, name):
        """The place id for a name (or variant) found in exactly one parish."""
        ks = {fold(name), fold(parse(name)[-1][0])} if name.strip() else set()
        hits = {pid for (parish, n), pid in self.place_index.items() if n in ks}
        parishes = {self.places[pid].get("parish") for pid in hits}
        return next(iter(hits)) if len(hits) == 1 and len(parishes) == 1 else None

    def label(self, pid):
        p = self.places.get(pid, {})
        return p.get("name") or pid.split("/", 1)[-1]

    # editing (fill-only)
    def add_parish(self, name, **fields):
        p = self.parishes.setdefault(name, {})
        for k, v in fields.items():
            if v not in ("", None) and p.get(k) in ("", None, [], ()):
                p[k] = v
        return p

    def add_alias(self, name, alias):
        p = self.parishes.setdefault(name, {})
        if fold(alias) != fold(name) and alias not in p.get("aliases", []):
            p["aliases"] = sorted(set(p.get("aliases", [])) | {alias})

    def add_place(self, parish, name, **fields):
        pid = f"{parish}/{name}"
        p = self.places.setdefault(pid, dict(name=name, parish=parish))
        for k, v in fields.items():
            if v not in ("", None) and p.get(k) in ("", None, [], ()):
                p[k] = v
        self._index()
        return pid

    def add_variant(self, pid, written):
        p = self.places[pid]
        if written and written != p.get("name", "") and written not in p.get("variants", []):
            p["variants"] = sorted(set(p.get("variants", [])) | {written})
            self._index()

    def add_written(self, parish, written):
        """Enter a written name: each level of parse() as its own place
        (a farm `within` its rote, a croft `within` its farm), the written
        form as a variant of the innermost one. Returns its id."""
        parent = None
        for name, kind in parse(written):
            pid = self.place_index.get((parish, fold(name)))
            if not pid:
                pid = self.add_place(parish, name, kind=kind, within=parent or "")
            else:                                             # fill-only
                if parent and not self.places[pid].get("within") and pid != parent:
                    self.places[pid]["within"] = parent
                if kind and not self.places[pid].get("kind"):
                    self.places[pid]["kind"] = kind
            parent = pid
        self.add_variant(parent, _clean(textfix.fix(written)))
        return parent

    def save(self):
        self.root.mkdir(exist_ok=True)
        (self.root / "parishes.toml").write_text(
            dump_toml(PARISH_HEADER, self.parishes, PARISH_FIELDS), encoding="utf-8")
        (self.root / "places.toml").write_text(
            dump_toml(PLACE_HEADER, self.places, PLACE_FIELDS), encoding="utf-8")


def load(cfg=None):
    import config
    cfg = cfg or config.load()
    return Gazetteer(ROOT, config.path(cfg, "plac_map.toml"))


# -- building from the tree's citations -------------------------------------------------

def _clean(name):
    return re.sub(r"\s+", " ", (name or "").strip(" ,.;"))


def _year(r):
    m = re.search(r"\d{4}", r.get("event_date") or r.get("years") or "")
    return int(m.group(0)) if m else None


STREET = re.compile(r"gatan\b|vägen\b|gränd\b|kvarteret|\bkv\.|torget\b", re.I)


def build(g, rows, parishes_info=None, extra_parishes=()):
    """Add parishes and places of record from volume rows (volumes.build).
    Returns proposals: (parish, [names]) clusters of likely variants."""
    parishes_info = parishes_info or {}
    for name in extra_parishes:
        g.add_parish(textfix.fix(name))
    for r in rows:
        name = r.get("parish")
        if not name or not (r.get("volume") or r.get("ra_code") or r.get("archive_code")):
            continue
        canon = g.parish(name) or name
        archive = (r.get("ra_code") or "").rsplit("/", 2)[0] or r.get("archive_code", "")
        info = parishes_info.get(name, {})
        g.add_parish(canon, archive=archive, archive_from=r.get("code_from", ""),
                     wikidata=info.get("qid", ""), label=info.get("label", ""),
                     lat=info.get("lat"), lon=info.get("lon"), harad=info.get("harad", ""))
        if r.get("ra_archive"):
            g.add_alias(canon, re.sub(r"\s+kyrkoarkiv.*", "", r["ra_archive"]))
    g._index()

    seen = defaultdict(Counter)
    for r in rows:
        parish = g.parish(r.get("parish") or "")
        name = _clean(r.get("farm"))
        if not parish or not name or re.search(r"\d", name) or STREET.search(name):
            continue
        of_record = r.get("tier") in ("mh-record", "ra-full", "ra-link")
        y = _year(r)
        if not of_record and not (y and y < 1950):
            continue
        seen[parish][name] += 1
    for parish, names in seen.items():
        for name, _ in names.most_common():
            g.add_written(parish, name)     # levels, `within` links, variant
    counts = Counter()
    for parish, names in seen.items():
        for name, n in names.items():
            for level, _ in parse(name):
                counts[(parish, level)] += n
            counts[(parish, name)] += n
    g.merged = getattr(g, "merged", []) + auto_merge(g, counts)
    return proposals(g)


# Words that tell farms of one village apart: names that differ in one of
# these are neighbours, not spellings ("Tuggarp Västergård" / "Östergård").
_SIDES = [("väst", r"v[äe]?st|vest|wst"), ("öst", r"öst|ost"), ("nor", r"nor"),
          ("söd", r"söd|sod|sön|son"), ("mel", r"mel"), ("sto", r"stor"),
          ("lil", r"lil"), ("övr", r"övr|ofr|övf"), ("ned", r"ned"), ("ny", r"ny"),
          ("gam", r"gaml")]
_SIDE = [(k, re.compile(rf"^(?:{rx})", re.I)) for k, rx in _SIDES]


def _distinct_words(a, b):
    """Names that differ in a word telling neighbouring farms apart
    (Väster/Öster, Norr/Söder, Stora/Lilla, ...) are different places."""
    def marks(s):
        out = set()
        for w in modern(s).lower().split():
            w = w.replace("w", "v")
            for k, rx in _SIDE:
                if rx.match(w) and (len(w) <= 6 or re.match(r"^(v[äe]?ster|öster|oster|norr|"
                                                             r"nore|söder|soder|södra|sodra|"
                                                             r"norra|västra|vestra|östra|"
                                                             r"mellan|stora|lilla|övre|nedre|"
                                                             r"nya|gamla|vst|wst)", w)):
                    out.add(k)
                    break
        return out
    return marks(a) != marks(b)


FILLER = re.compile(r"\b(hemman|hemmanet|byn|nr|n:o|no)\b\.?|[():]", re.I)
# A farm word cut short in the books: "Mellang", "Skatteg.", "Riddareg", "Smedsgt"
_GARD_CUT = re.compile(r"(?<=\w{3})g(?:t|s|\.)?$")


def ortho(name):
    """A looser key for *automatic* merging: historic orthography evened out
    on top of fold(): e/ä, o/å/ö, kj/k, -gården/-gård, genitive s, filler
    words ("Hemman."). Used only within one parish, never across."""
    s = fold(modern(FILLER.sub(" ", name or "")))
    for a, b in (("gårdens", "gård"), ("gården", "gård"), ("ä", "e"), ("å", "o"), ("ö", "o"),
                 ("kj", "k")):
        s = s.replace(a, b)
    s = re.sub(r"[dt]s(?=torp)|d(?=storp)", "s", s)        # Algud-/Algut-/Algustorp
    s = re.sub(r"(?<=[aeiouyåäö])h(?=[^aeiouyåäö\s])|(?<=d)h", "", s)   # Sundsdahlen, Dahl
    s = " ".join(re.sub(rf"(?<=[{_C}])s$", "", w) for w in s.split())
    return re.sub(r"([a-z])\1+", r"\1", s)


def _no_e(s):
    return re.sub(r"(?<=\w)e(?=\w)", "", s)


def _loose(s):
    """Second-tier key: cut-short gård written out, joint s/d between
    consonants dropped (Valdshult/Valshult, Svenhult/Svenshult), -stad as
    -sta, f as v, a/å/o as one vowel (Grimsas/Grimsås, -tarp/-torp)."""
    words = []
    for w in s.split():
        w = _GARD_CUT.sub("gård", w) if not w.endswith("gård") else w
        words.append(w)
    s = " ".join(words)
    s = re.sub(r"stad\b", "sta", s).replace("f", "v")
    s = re.sub(rf"(?<=[{_C}])[sd](?=[{_C}])", "", s)
    s = re.sub(r"[åo]", "a", s)
    return re.sub(r"([a-zåäö])\1+", r"\1", _no_e(s))


def clear_variant(a, b):
    """True when two names in one parish are the same place written two
    ways: equal under ortho(); or equal once unstressed e's are dropped
    ("Storegården"/"Storgården", "Måleskog"/"Målskog") and close overall;
    or equal under the looser _loose() key and close overall. Neighbour
    farms (Väster-/Öster-, Norra/Södra, Stora/Lilla) never merge."""
    fa, fb = ortho(a), ortho(b)
    if _distinct_words(a, b) or len(fa) < 4:
        return False
    if fa == fb:
        return True
    close = difflib.SequenceMatcher(None, fa, fb).ratio()
    if _no_e(fa) == _no_e(fb) and close >= 0.85:
        return True
    return _loose(fa) == _loose(fb) and close >= 0.8


def merge(g, keep, drop):
    """Fold place `drop` into `keep`: its name and variants become variants,
    `within` links to it move to `keep`. Checked entries are never dropped."""
    d = g.places.pop(drop)
    k = g.places[keep]
    names = {d.get("name", "")} | set(d.get("variants", []))
    k["variants"] = sorted((set(k.get("variants", [])) | names) - {k.get("name")})
    for f in ("lat", "lon", "tora", "kind", "within", "note"):
        if not k.get(f) and d.get(f):
            k[f] = d[f]
    for p in g.places.values():
        if p.get("within") == drop:
            p["within"] = keep
    if k.get("within") == keep:
        k.pop("within")


# Common endings of Swedish farm and village names, correctly spelled.
SUFFIX = re.compile(r"(gård|gården|torp|torpet|hult|ryd|by|byn|berg|näs|bo|stad|sta|"
                    r"arp|holm|lid|mon|mo|ås|sjö|vik|dal|dalen|kulla|hög|tofta|bol|"
                    r"strand|säter|hagen|hage|backe|backen|mad|ed|rud|red|ö)$", re.I)


def best_name(g, pid, counts):
    """The prettiest of a place's written forms, in modern spelling: not a
    genitive of another form, abbreviations written out, the most å/ä/ö
    (modern orthography over e/o spellings), then the most frequent."""
    p = g.places[pid]
    written = [p.get("name", "")] + list(p.get("variants", []))
    cands = {}
    for w in written:
        for level, _ in parse(w)[-1:]:
            cands.setdefault(level, 0)
            cands[level] += counts.get((p.get("parish"), w), 0) + counts.get((p.get("parish"), level), 0)
    folds = {fold(c) for c in cands}
    def score(c):
        genitive = c.endswith("s") and fold(c[:-1]) in folds
        proper = bool(SUFFIX.search(c))
        return (not genitive, "." not in c, proper, sum(ch in "åäöÅÄÖ" for ch in c), cands[c], c)
    return max(cands, key=score)


def rename(g, pid, name):
    """Give a place a new display name; its id follows ("Parish/Name"), the
    old name stays a variant, `within` links follow."""
    p = g.places[pid]
    if name == p.get("name"):
        return pid
    new = f"{p['parish']}/{name}"
    if new in g.places and new != pid:
        return pid
    old = p.get("name")
    p["name"] = name
    p["variants"] = sorted((set(p.get("variants", [])) | {old}) - {name})
    g.places[new] = g.places.pop(pid)
    for q in g.places.values():
        if q.get("within") == pid:
            q["within"] = new
    return new


def auto_merge(g, counts=None):
    """Merge clear variants within each parish. The entry kept is the one
    whose names were written most often in the records (counts: written
    name -> n), else the checked one. Returns [(parish, kept, [dropped])]."""
    counts = counts or {}
    weight = lambda pid: (bool(g.places[pid].get("checked")),
                          sum(counts.get((g.places[pid].get("parish"), n), 0)
                              for n in [g.label(pid)] + g.places[pid].get("variants", [])))
    by_parish = defaultdict(list)
    for pid, p in g.places.items():
        by_parish[p.get("parish", "")].append(pid)
    done = []
    for parish, pids in sorted(by_parish.items()):
        groups = []                                    # union of clear pairs
        for pid in sorted(pids):
            hit = [grp for grp in groups if any(clear_variant(g.label(pid), g.label(o)) for o in grp)]
            new = {pid}.union(*hit) if hit else {pid}
            groups = [grp for grp in groups if grp not in hit] + [new]
        for grp in groups:
            if len(grp) < 2:
                continue
            keep = max(sorted(grp), key=weight)
            dropped = [x for x in sorted(grp) if x != keep and not g.places[x].get("checked")]
            names = sorted({g.label(x) for x in grp})
            for x in dropped:
                merge(g, keep, x)
            if dropped:
                if not g.places[keep].get("checked"):
                    keep = rename(g, keep, best_name(g, keep, counts))
                done.append((parish, keep, [n for n in names if n != g.label(keep)]))
    g._index()
    return done


def proposals(g, cutoff=0.8):
    """Likely variants not yet joined: names in one parish whose folded
    forms are close (difflib ratio >= cutoff), or one ending in the other
    ("Skogs Algutstorp" ~ "Algutstorp", a part or an alternative name)."""
    by_parish = defaultdict(list)
    for pid, p in g.places.items():
        by_parish[p.get("parish", "")].append(pid)
    out = []
    for parish, pids in sorted(by_parish.items()):
        pids = sorted(pids)
        for i, a in enumerate(pids):
            for b in pids[i + 1:]:
                fa, fb = fold(g.label(a)), fold(g.label(b))
                r = difflib.SequenceMatcher(None, fa, fb).ratio()
                part = fa.endswith(" " + fb) or fb.endswith(" " + fa)
                if (r >= cutoff or part) and not _distinct_words(g.label(a), g.label(b)) \
                        and not (g.places[a].get("within") == b or g.places[b].get("within") == a):
                    out.append((parish, a, b, round(r, 2), "part of / alternative" if part
                                else "spelling"))
    return out


def wikidata_fill(g, wd):
    """Wikidata item and coordinates for parishes that have an archive code
    but no item yet (one search per code; coordinates from the church
    parish or, failing that, the socken it replaced)."""
    import places
    for name, p in sorted(g.parishes.items()):
        if p.get("wikidata") or not p.get("archive"):
            continue
        try:
            items = places.items_for_code(wd, p["archive"])
        except Exception as ex:
            print(f"  {name}: {ex.__class__.__name__}")
            continue
        if not items:
            continue
        info = places.parish(wd, items[0])
        lat = lon = None
        harad = ""
        for q in [items[0]] + [l["item"] for l in info["replaces"] if l["item"]]:
            e = wd.entity(q)
            c = places._claims(e, "P625")
            if not harad and q != items[0]:
                h = places._claims(e, "P131")
                harad = wd.label(h[0][0]) if h and h[0][0] else ""
            if c and isinstance(c[0][0], dict):
                lat, lon = c[0][0]["latitude"], c[0][0]["longitude"]
                break
        g.add_parish(name, wikidata=items[0], label=info["label"],
                     lat=round(lat, 4) if lat else None, lon=round(lon, 4) if lon else None,
                     harad=harad)


def write_todo(path, g, props, rows):
    """Review list: variant proposals and place strings that resolve to no
    parish (most frequent first)."""
    lines = ["# Gazetteer to-do (generated; private)", "",
             "Accept a proposal by adding one name to the other's `variants` in",
             "gazetteer/places.toml (or set `within` for a part of a village), then",
             "delete the redundant entry. Fix a single odd string in data/plac_map.toml.", "",
             "## Likely variants", ""]
    for parish, a, b, r, why in props:
        lines.append(f"- {parish}: **{g.label(a)}** ~ **{g.label(b)}** ({why}, {r})")
    merged = getattr(g, "merged", [])
    lines += ["", f"## Merged automatically this run ({len(merged)})", "",
              "Clear spelling variants (e/ä, o/å/ö, kj/k, -gården/-gård, gd = gård,",
              "genitive s, dropped e). Undo one by moving the name out of `variants`",
              "into an entry of its own with `checked = true`.", ""]
    lines += [f"- {parish}: **{g.label(k)}** ← " + ", ".join(ds)
              for parish, k, ds in merged]
    unresolved = Counter(r.get("event_place") for r in rows
                         if r.get("event_place") and not g.parish(r.get("parish") or "")
                         and r.get("tier") == "plac-only")
    lines += ["", f"## Place strings with no known parish ({len(unresolved)})", "",
              "Add the parish to gazetteer/parishes.toml (or an alias), or map the",
              "string in data/plac_map.toml.", ""]
    lines += [f"- {n} × {s}" for s, n in unresolved.most_common(150)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")   # BOM: some viewers guess Latin-1


# -- command line -------------------------------------------------------------------------

def _main(argv):
    import config
    import volumes
    cfg = config.load()
    g = load(cfg)
    cmd = argv[0] if argv else "build"
    if cmd == "build":
        before = (len(g.parishes), len(g.places))
        # Resolution feeds back (a place added now lets the next pass place
        # more strings), so repeat until the files stop changing.
        for _ in range(3):
            snap = (dump_toml("", g.parishes, PARISH_FIELDS), dump_toml("", g.places, PLACE_FIELDS))
            rows, parishes_info, _ = volumes.run(cfg, wikidata=False, gazetteer=g)
            props = build(g, rows, parishes_info,
                          (cfg.get("volumes") or {}).get("parishes", []))
            if snap == (dump_toml("", g.parishes, PARISH_FIELDS),
                        dump_toml("", g.places, PLACE_FIELDS)):
                break
        if "--wikidata" in argv:
            import places
            wd = places.Wikidata(CACHE / "wikidata.json")
            try:
                wikidata_fill(g, wd)
            finally:
                wd.save()
        g.save()
        write_todo(config.path(cfg, "gazetteer_todo.md"), g, props, rows)
        print(f"parishes {before[0]} -> {len(g.parishes)}, places {before[1]} -> "
              f"{len(g.places)}; {len(props)} variant proposals in data/gazetteer_todo.md")
    elif cmd == "show":
        rx = re.compile(" ".join(argv[1:]), re.I)
        for pid, p in sorted(g.places.items()):
            if rx.search(pid) or any(rx.search(v) for v in p.get("variants", [])):
                print(pid, {k: v for k, v in p.items() if k not in ("name", "parish")})
        for name, p in sorted(g.parishes.items()):
            if rx.search(name):
                print(name, p)
    else:
        print(__doc__)


if __name__ == "__main__":
    _main(sys.argv[1:])
