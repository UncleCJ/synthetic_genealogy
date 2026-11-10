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
data/output/gazetteer_todo.md for a person to accept by adding a variant.

Before matching, a written name is reduced to one name: of "A eller B"
the last alternative is kept ("Duve eller Dårebo" -> Dårebo), a parish
written in front is dropped ("Gr. Landsförsaml. Björket" -> Björket), and
a known village or rote in front of a known farm becomes `within`
("Skogs Hjulshult" -> Hjulshult within Skogs rote; split_known). Each
build re-applies these rules to unchecked entries (reresolve), so a new
rule, variant or merge cleans up what earlier runs added.

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
    python gazetteer.py build --wikidata   # also fetch archive codes (Riksarkivet),
                                           # Wikidata items and coordinates
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
    s = re.sub(r"\b([Vv])[eä]?st(?=er|ra\b|an)", r"\1äst", s)  # Vestergård, Vstergård -> Väster-
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
_UNDER = re.compile(r"^(?P<croft>.+?)\s+under\s+(?P<farm>.+)$", re.I)    # "Moen under Askaremålen"
_TORP_ALONE = re.compile(r"^(?:Torpet|Torp|T\.)\s+(?P<croft>.+)$")
# "Gr. Landsförsaml. Björket", "Gr. Lunds Församling Björket": the parish
# written in front of the place (here Gränna landsförsamling)
_DESIGNATOR = re.compile(r"^(?:\S+\.?\s+)?(?:lands?\s*förs\w*|lunds?\s+förs\w*|församl\w*)\.?\s+",
                         re.I)
_ELLER = re.compile(r"\s*\beller\b\.?\s*", re.I)
# A farm's jordnatur (who owned it and took its rent: skatte, krono, frälse
# and mixed kinds) written beside its name: "Possarp Skatte", "Skatte
# Porssarp", "Mantal Elmtomta Södergård Frälse". It states the farm's legal
# status, which can change (krono bought to skatte), so it is not part of
# the name. As a compound ("Ödeshögs Skattegård") it is a name: see FARM_TYPE.
_JN = r"(?:skatte|krono|fr[äe]lse)(?:-?(?:skatte|krono|fr[äe]lse))?"
_JORDNATUR = re.compile(rf"^(?:mantal\.?\s+)?(?:(?P<pre>{_JN})\.?\s+)?(?P<name>.+?)(?:\s+(?P<post>{_JN})\.?)?$", re.I)


def jordnatur(written):
    """(name without it, jordnatur or ''): 'Possarp Skatte' -> ('Possarp',
    'skatte'), 'Skatte Porssarp' -> ('Porssarp', 'skatte'), 'Mantal Elmtomta
    Södergård Frälse' -> ('Elmtomta Södergård', 'frälse'). A bare 'Skatte'
    or a compound ('Skattegård') stays as written."""
    m = _JORDNATUR.match((written or "").strip())
    if not m or not (m["pre"] or m["post"] or re.match(r"mantal\b", written.strip(), re.I)):
        return written, ""
    jn = (m["pre"] or m["post"] or "").lower().replace("-", "").replace("frelse", "frälse")
    return m["name"], jn


def unalias(written):
    """One name for a place written with alternatives: the last one, which
    is usually the name in use ('Duve eller Dårebo' -> 'Dårebo'); an
    indexer's fragment that starts with 'Eller' loses it ('Eller Kjellerö
    Högaberg' -> 'Kjellerö Högaberg'); a parish written in front goes
    ('Gr. Landsförsaml. Björket' -> 'Björket'). The earlier alternative is
    not kept as a name of the place: it may be a farm of its own."""
    s = jordnatur(_DESIGNATOR.sub("", _clean(textfix.fix(written))))[0]
    parts = [x for x in _ELLER.split(s) if x.strip(" .")]
    return parts[-1] if parts else s


def parse(raw):
    """A written place name -> [(display name, kind)], outermost first:
    'Roten Ingarp Rote Swenshult' -> [('Ingarps rote', 'rote'), ('Svenshult', '')]
    'Swenshult Torpet Swenstorp'  -> [('Svenshult', ''), ('Svenstorp', 'torp')]
    'Moen under Askaremålen'      -> [('Askaremålen', ''), ('Moen', 'torp')]
    'Duve eller Dårebo'           -> [('Dårebo', '')]   (unalias)
    Heuristic: only the rote and torp patterns are taken apart; a village
    or rote written in front of a farm ('Skogs Hjulshult') needs the
    gazetteer to be recognised (Gazetteer.split_known)."""
    s = re.sub(r"(?<=[a-zåäö])(?=[A-ZÅÄÖ])", " ", unalias(raw))
    for rx in _ROTE:
        m = rx.match(s)
        if m:
            chain = [(rote_name(m["rote"]), "rote")]
            return chain + (parse(m["rest"]) if m.groupdict().get("rest") else [])
    m = _UNDER.match(s)
    if m:
        return parse(m["farm"]) + [(modern(m["croft"]), "torp")]
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
                "geo_level", "geo_source", "tora", "jordnatur", "note", "checked"]

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
#   jordnatur skatte | krono | frälse | ..., as the records state it (a list:
#             it can change over time)
#   checked   true once a person has looked at the entry
# A rebuild only adds entries and fills empty fields. Rename by adding the
# old name as a variant, so the id stays stable.
"""


# -- the gazetteer ----------------------------------------------------------------------

# A part of a farm or village rather than a place of its own: on its own it
# names dozens of places ("Sörgården", "Norrgård", "Torpet").
GENERIC = re.compile(r"^(?:(?:s[öo]r|s[öo]der|norr?|[öo]ster|v[äe]ster|mellan|stor|lill|nya|gamla|"
                     r"övre|nedre|ytter|inner)e?\s?g[åa]rd(?:en)?|gården|torpet|bygget|backen|"
                     r"stugan|byn|(?:skatte|krono|fr[äe]lse|riddare|präst|bya?)(?:g[åa]rd(?:en)?)?)$", re.I)


# Kinds of farm: neighbouring farms of one village differ by them
# ("Ödeshögs Riddaregård" / "Ödeshögs Skattegård"), and on their own they
# name no particular place.
FARM_TYPE = re.compile(r"\b(?:bya?g[åa]rd|skatte|riddare|frälse|krono|kyrko|präst|g[äa]st|rusthåll|säteri|"
                       r"l[äöe]nsman|dräng|soldat|knekt|skolhus|stenhugger)", re.I)


def generic(name):
    return bool(GENERIC.match((name or "").strip(" .")))


def _part(name):
    """A part or kind of farm rather than a name of its own, also when cut
    short ('Storgl', 'Södergl', 'Mellang', 'Säterier')."""
    n = re.sub(r"(?<=\w{3})g(?:l|t|s|\.)?$", "gård", (name or "").strip(" ."))
    return generic(n) or bool(FARM_TYPE.search(n))


# What follows a parish's name in a place string or an archive label:
# "Källeryds socken", "Gränna landsförsamling", "Gränna lf.". Dropped before
# the lookup; a genitive s left behind ("Källeryds") is dropped after it.
PARISH_SUFFIX = re.compile(r"\s+(socken|lands- och stadsförsamling|lands?\.?\s*f[öo]rs\w*|stadsförsamling|"
                           r"församling|kyrkoförsamling|kyrka|lf\.?|sf\.?)\.?$", re.I)


# What may follow a place in a string without being its parish: county
# (also as MyHeritage writes it in an address, "Älvsborgs"), province,
# country. Anything else after a name could be a parish not yet in the
# gazetteer.
PROVINCES = {"skåne", "blekinge", "halland", "småland", "öland", "gotland", "västergötland",
             "östergötland", "bohuslän", "dalsland", "värmland", "närke", "södermanland",
             "uppland", "västmanland", "dalarna", "gästrikland", "hälsingland", "härjedalen",
             "jämtland", "medelpad", "ångermanland", "västerbotten", "norrbotten", "lappland"}
COUNTIES = {"stockholms", "stockholms stad", "uppsala", "södermanlands", "östergötlands",
            "jönköpings", "kronobergs", "kalmar", "gotlands", "blekinge", "kristianstads",
            "malmöhus", "skåne", "hallands", "göteborgs och bohus", "älvsborgs", "skaraborgs",
            "västra götaland", "värmlands", "örebro", "västmanlands", "kopparbergs", "dalarnas",
            "gävleborgs", "västernorrlands", "jämtlands", "västerbottens", "norrbottens"}
COUNTRIES = {"sverige", "sweden", "norge", "norway", "danmark", "denmark", "finland", "usa",
             "united states", "amerika"}


MOVE = re.compile(r"^\s*(?:fr\.|från)\s+.+?\s+(?:t\.|till)\s+(?P<to>.+)$", re.I)


def plac_parts(plac):
    """A place string as its comma-separated parts, repaired (textfix). A
    move written as one string ("fr. Aronsdal, Örgryte t. Haneström,
    Fuxerna", "fr. Partille t. Fuxerna") gives its destination only. The
    one splitter for volumes.normalise and Gazetteer.explain_plac."""
    s = textfix.fix(plac or "")
    m = MOVE.match(s)
    if m:
        s = m["to"]
    return [x.strip() for x in s.split(",") if x.strip()]


# A county letter after a parish ("Källeryd (F)", F = Jönköpings län;
# "Lane-Ryr (O)"): only a disambiguator, dropped before matching.
COUNTY_CODE = re.compile(r"\s*\((?:[A-ZÅÄÖ]{1,2})\)\s*$")


def drop_county_code(name):
    return COUNTY_CODE.sub("", name or "")


def region(part):
    """A county, province or country, not a place within a parish."""
    k = re.sub(r"\s+", " ", (part or "").lower().strip(" .,"))
    k = re.sub(r"\s+län$", "", k)
    return k in PROVINCES or k in COUNTIES or k in COUNTRIES


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
        # a variant with its jordnatur ("Possarp Skatte") also names the farm
        # without it ("Possarp"), unless that is a place of its own
        for pid, p in self.places.items():
            for n in list(p.get("variants", [])):
                bare, jn = jordnatur(n)
                if jn:
                    self.place_index.setdefault((p.get("parish", ""), fold(bare)), pid)

    # lookups
    def parish_rule(self, name):
        """(canonical parish or None, rule): the name as written or an alias,
        then with a suffix dropped ("Källeryds socken"), then the genitive s."""
        name = drop_county_code(name)
        f = fold(name)
        if f in self.parish_index:     # 'Skellefteå landsförsamling' as a parish of its own
            canon = self.parish_index[f]
            return canon, "parish name" if f == fold(canon) else "parish alias"
        k = fold(PARISH_SUFFIX.sub("", (name or "").strip()))
        if k in self.parish_index:
            return self.parish_index[k], "parish, suffix dropped"
        if k.endswith("s") and k[:-1] in self.parish_index:
            return self.parish_index[k[:-1]], "parish, genitive s dropped"
        return None, ""

    def parish(self, name):
        """Canonical parish name for a spelling, archive genitive included."""
        return self.parish_rule(name)[0]

    def place_rule(self, parish, name):
        """(place id or None, rule) for a written name: as written (name,
        variant, or variant without its jordnatur), else by its parsed
        innermost part ('Roten Ingarp Rote Swenshult' -> Svenshult), else
        a known village followed by a known place (split_known)."""
        parish = self.parish(parish) or parish
        if not name:
            return None, ""
        f = fold(name)
        pid = self.place_index.get((parish, f))
        if pid:
            if f == fold(self.label(pid)):
                return pid, "place name"
            if any(fold(v) == f for v in self.places[pid].get("variants", [])):
                return pid, "place variant"
            return pid, "variant without jordnatur"
        pid = self.place_index.get((parish, fold(parse(name)[-1][0])))
        if pid:
            return pid, "parse(): innermost level"
        split = self.split_known(parish, name)
        return (split[1], "split_known (village + place, ortho)") if split else (None, "")

    def place(self, parish, name):
        """Place id for a written name (place_rule)."""
        return self.place_rule(parish, name)[0]

    def _known(self, parish, name, exclude=None):
        """An existing place in the parish for a name: as written, by its
        parsed innermost part, or equal under ortho() (Kjellshyltan ~
        Källshyltan)."""
        for n in (name, parse(name)[-1][0]):
            hit = self.place_index.get((parish, fold(n)))
            if hit and hit != exclude:
                return hit
        o = ortho(parse(name)[-1][0])
        hits = {pid for (par, n), pid in self.place_index.items()
                if par == parish and pid != exclude and ortho(n) == o}
        return next(iter(hits)) if len(hits) == 1 else None

    def split_known(self, parish, name, exclude=None):
        """(village or rote id, place id) when a name is a known village or
        rote of the parish followed by a known place in it: 'Skogs Hjulshult'
        -> (Skogs rote, Hjulshult), 'Kjellerö Högaberg' -> (Källerö,
        Högaberg). The place must be a name of its own, not a part
        ('Tuggarp Västergård') or a kind of farm ('Ödeshögs Skattegård')."""
        words = parse(name)[-1][0].split()
        if len(words) < 2:
            return None
        head, rest = words[0], " ".join(words[1:])
        if _part(rest) or _part(head):
            return None
        parent = None
        for n in (head, re.sub(rf"(?<=[{_C}])s$", "", head), rote_name(head)):
            parent = self.place_index.get((parish, fold(n)))
            if parent:
                break
        if not parent or parent == exclude:
            return None
        pid = self._known(parish, rest, exclude)
        if not pid or pid == parent or pid in _ancestors(self, parent) \
                or _part(self.label(pid)):                    # 'Göhestra, Hagelstorp'
            return None
        within = self.places[pid].get("within")
        return (parent, pid) if within in (None, "", parent) or self.places.get(within, {}).get(
            "within") == parent else None

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

    def explain_plac(self, plac):
        """(id, rule, parish rule, part used) for a whole place string
        ("Torpet Ödelyckan, Adelöf, Adelöv, Jönköpings län, Sverige"). The
        id is a gazetteer place, or "parish:<name>" when only the parish is
        known. Order: plac_map; the first part that is a known parish, with
        the parts before it tried as a place (neighbouring parts joined
        first: "Finnanäs, Norrgård" -> Finnanäs Norrgård, then each part,
        most specific first); else a village name unique to one parish,
        but only when nothing but county, province or country follows it
        ("Hagelstorp, Jönköpings län"), a kommun, another place of that
        parish, or the parish's own name misspelt ("Källaryd"): in "Storegården, Fuxerna, Älvsborgs" the unknown "Fuxerna"
        may be the parish, so a Storgården elsewhere is no answer."""
        if not plac:
            return None, "", "", ""
        key = textfix.fix(plac)
        if key in self.plac_map:
            return self.plac_map[key].get("place"), "plac_map", "", ""
        parts = plac_parts(key)
        for k, x in enumerate(parts):
            par, prule = self.parish_rule(x)
            if not par:
                continue
            before = parts[:k]
            pairs = [f"{a} {b}" for a, b in zip(before, before[1:])]
            for i, t in enumerate(pairs + [y for y in before if not generic(y)]):
                pid, rule = self.place_rule(par, t)
                if pid and not generic(self.label(pid)):
                    return pid, rule + (" (two parts joined)" if i < len(pairs) else ""), prule, t
            return f"parish:{par}", "parish only" + (" (farm part unknown)" if before else ""), prule, x
        for i, x in enumerate(parts):
            pid = None if region(x) else self.unique_place(x)
            par = self.places[pid].get("parish") if pid else None
            if pid and all(region(y) or self._near_parish(y, par) or self.place(par, y)
                           for y in parts[i + 1:]):
                return pid, "unique village name", "", x
        return None, "unresolved", "", ""

    def _near_parish(self, part, parish):
        """A part that may stand after a place of `parish` without naming
        another parish: a kommun, or the parish itself however written
        ("Källaryd")."""
        if re.search(r"\bkommun\b|\bkn\b", part or "", re.I):
            return True
        a = fold(PARISH_SUFFIX.sub("", drop_county_code(part)).strip())
        b = fold(parish or "")
        return bool(a and b) and (a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.8)

    def resolve_plac(self, plac):
        """A whole place string -> (id, how); how is "plac_map", "gazetteer",
        "unique village name", "parish" or "" (unresolved). The rule in
        detail: explain_plac."""
        pid, rule, _, _ = self.explain_plac(plac)
        if rule in ("", "unresolved"):
            return None, ""
        if rule in ("plac_map", "unique village name"):
            return pid, rule
        return pid, "parish" if rule.startswith("parish only") else "gazetteer"

    def coords(self, pid):
        """(lat, lon, level, source) for a place id or "parish:<name>", using
        the place it lies within, then its parish, when it has no point."""
        if not pid:
            return None
        if pid.startswith("parish:"):
            p = self.parishes.get(pid[7:], {})
            return (p["lat"], p["lon"], "parish", "wikidata") if p.get("lat") else None
        p = self.places.get(pid, {})
        if p.get("lat"):
            return p["lat"], p["lon"], p.get("geo_level", "farm"), p.get("geo_source", "")
        seen = {pid}
        w = p.get("within")
        while w and w not in seen and w in self.places:     # the village it lies in
            seen.add(w)
            q = self.places[w]
            if q.get("lat"):
                return q["lat"], q["lon"], "village", f"within:{w}"
            w = q.get("within")
        return self.coords(f"parish:{p['parish']}") if p.get("parish") else None

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
        known = any((parish, fold(n)) in self.place_index    # a checked 'Näs Hagelstorp'
                    for n in (written, parse(written)[-1][0]))
        split = None if known else self.split_known(parish, written)
        if split:                                             # 'Skogs Hjulshult'
            parent, pid = split
            if not self.places[pid].get("within") and \
                    not any(q.get("within") == pid for q in self.places.values()):
                self.places[pid]["within"] = parent
            self.add_variant(pid, _clean(textfix.fix(written)))
            return pid
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


# Not places: "of no fixed abode", "in the parish", "unknown"
NONPLACE = re.compile(r"^(?:på socknen|i socknen|socknen|utan (?:bestämd|fast|känd) (?:bostad|hemvist)|"
                      r"obefintlig[ae]?|okänd(?: ort)?|ej känd|flyttad|utflyttad|död)$", re.I)
STREET = re.compile(r"gatan\b|gat\.?$|vägen\b|gränd\b|kvarteret|\bkv\.|torget\b", re.I)
# Circumstances written where a place should be: kept out of the public file.
PERSONAL = re.compile(r"foster|fattig(?:hjon|vård)|\bhos\b|\binhyst|\bpiga\b|\bdräng\b", re.I)


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
        if not parish or not name or re.search(r"\d", name) or STREET.search(name) \
                or NONPLACE.match(name) \
                or PERSONAL.search(name) or g.parish(name) == parish or region(name) \
                or _near_county(name):
            # (the parish itself, a country or county, a circumstance)
            continue
        of_record = r.get("tier") in ("mh-record", "ra-full", "ra-link")
        y = _year(r)
        if not of_record and not (y and y < 1950):
            continue
        seen[parish][name] += 1
    for parish, names in seen.items():
        for name, _ in names.most_common():
            g.add_written(parish, name)     # levels, `within` links, variant
    g.merged = getattr(g, "merged", []) + reresolve(g)
    fill_jordnatur(g)
    counts = Counter()
    for parish, names in seen.items():
        for name, n in names.items():
            for level, _ in parse(name):
                counts[(parish, level)] += n
            counts[(parish, name)] += n
    g.merged = getattr(g, "merged", []) + auto_merge(g, counts)
    return proposals(g)


def _near_county(name):
    """A county name misspelt as a farm ("Älsvborg", "Alvsborg")."""
    k = re.sub(r"\s+län$", "", name or "", flags=re.I).lower()
    return any(difflib.SequenceMatcher(None, k, c.rstrip("s")).ratio() >= 0.85 for c in COUNTIES)


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
    kind = lambda s: {re.sub(r"[aeäö]", "", m.group(0).lower())[:3]       # läns ~ löns
                      for m in FARM_TYPE.finditer(modern(s))}
    ta, tb = kind(a), kind(b)
    return marks(a) != marks(b) or bool(ta and tb and ta != tb)


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


def fill_jordnatur(g):
    """Record on each place the jordnaturer its written forms state, as a
    list (it can change over time: krono bought to skatte). Fill-only."""
    for p in g.places.values():
        seen = {jordnatur(n)[1] for n in [p.get("name", "")] + list(p.get("variants", []))} - {""}
        if seen - set(p.get("jordnatur", [])):
            p["jordnatur"] = sorted(seen | set(p.get("jordnatur", [])))


def reresolve(g):
    """Bring unchecked entries in line with the current naming rules, so a
    new rule cleans up what earlier runs added: an entry whose name now
    resolves to another place ('Duve Eller Dårebo' -> Dårebo, 'Skogs
    Hjulshult' -> Hjulshult within Skogs rote) is merged into it; one whose
    name only reads differently now ('Ryssebo eller Folarp' -> Folarp,
    'Kalfhult Vestergård' -> Kalfhult Västergård) is renamed. Returns
    [(parish, kept, [old names])] like auto_merge."""
    done = []
    changed = True
    while changed:
        changed = False
        for pid in sorted(g.places):
            p = g.places[pid]
            if p.get("checked"):
                continue
            parish, name = p.get("parish", ""), g.label(pid)
            split = g.split_known(parish, name, exclude=pid)
            target = split[1] if split else None
            if not target:
                inner = parse(name)
                hit = g.place_index.get((parish, fold(inner[-1][0])))
                target = hit if hit != pid and len(inner) == 1 else None
            if target and pid not in _ancestors(g, target):
                merge(g, target, pid)
                if split and not g.places[target].get("within") and split[0] != target \
                        and not any(q.get("within") == target for q in g.places.values()):
                    g.places[target]["within"] = split[0]
                g._index()
                done.append((parish, target, [name]))
                changed = True
                break
            new = parse(name)
            if len(new) == 1 and new[0][0] != name and f"{parish}/{new[0][0]}" not in g.places:
                rename(g, pid, new[0][0])
                g._index()
                done.append((parish, f"{parish}/{new[0][0]}", [name]))
                changed = True
                break
    return done


def _ancestors(g, pid):
    seen = []
    while pid in g.places and pid not in seen:
        seen.append(pid)
        pid = g.places[pid].get("within")
    return seen


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
        # Online (--wikidata), Riksarkivet is asked too: a parish new to the
        # gazetteer gets its archive code there, and wikidata_fill finds
        # its item and coordinates by that code.
        online = "--wikidata" in argv
        for _ in range(3):
            snap = (dump_toml("", g.parishes, PARISH_FIELDS), dump_toml("", g.places, PLACE_FIELDS))
            rows, parishes_info, _ = volumes.run(cfg, wikidata=False, gazetteer=g,
                                                 riksarkivet_lookups=online)
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
              f"{len(g.places)}; {len(props)} variant proposals in data/output/gazetteer_todo.md")
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
