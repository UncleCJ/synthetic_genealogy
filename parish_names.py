"""
Every Swedish parish name, so that a place string can name a parish the
family's own citations never mention.

`gazetteer/parish_names.tsv` holds every socken (Q1523821) and församling
(Q615980) item on Wikidata in Sweden: its label, aliases, Riksarkivet
archive code (P5324), county, coordinates, and the items it was replaced
by (P1366) or replaced (P1365). It is public data (Wikidata, CC0), built
once with `python3 parish_names.py build` and committed.

`Names` indexes the forms a parish is written in, all folded
(gazetteer.fold):

- the label without its kind: "Barkeryds socken" -> "Barkeryds", and
  without the genitive s, "Barkeryd" (gazetteer's rule: an s after a
  consonant); likewise "stadsförsamling", "landsförsamling",
  "domkyrkoförsamling" and the like;
- the aliases, treated the same way;
- a town's congregation without the town: "Norrköpings Östra Eneby" ->
  "Östra Eneby", with the town ("Norrköping") kept so a string that names
  it can prefer that congregation;
- abbreviations: "Ö. Eneby", "N. Sandby", "V. Tollstad", "St. Malm".

A name gives candidates; each candidate is a parish *group*: a socken and
the församlingar it became (and back), since a place string written as
"X socken" and a volume of "X församling" mean one parish to the records
half. `candidates(name, counties)` narrows them by a county written in the
same string.

Sketch status: unvalidated beyond two family trees. Wikidata's P131 has no
dates, so the county is today's (or the last one); a parish that moved
county is narrowed wrongly. The genitive rule loses a final s of names
that have one ("Fors" -> "For" is also indexed; the plain form is too).
"""
import csv
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import gazetteer

PATH = gazetteer.ROOT / "parish_names.tsv"
KOMMUNER = gazetteer.ROOT / "kommuner.txt"
SPARQL = "https://query.wikidata.org/sparql"
UA = "synthetic-genealogy/0.1 (https://github.com/UncleCJ/synthetic_genealogy)"
COLUMNS = ["qid", "kind", "label", "aliases", "archive", "county", "lat", "lon",
           "succ", "pred"]

# What follows a parish's own name in its label or in a place string.
KIND = re.compile(r"\s+(?:lands- och stadsförsamling|(?:stads|lands|domkyrko|kyrko|slotts|amiralitets)?"
                  r"(?:församling|förs\.?)|socken|sn\.?|kyrka|kyrkobokföringsdistrikt|distrikt)$", re.I)
# A label whose parish is a town's own ("Ystads stadsförsamling",
# "Linköpings domkyrkoförsamling"): the town's name alone does not name it.
TOWN_KIND = re.compile(r"\s+(?:lands- och stadsförsamling|stadsförsamling|domkyrkoförsamling)$", re.I)
# A congregation named after its town: "Norrköpings Östra Eneby",
# "Ystads Sankta Maria", "Sigtuna Sankt Olof och Sankt Per" is not one
# (no genitive), nor "Västra Eneby" (a direction, not a town).
TOWN_PREFIX = re.compile(r"^(?P<town>[A-ZÅÄÖ][\wåäöé\-]+?s)\s+(?P<rest>[A-ZÅÄÖ].+)$")
NOT_TOWN = {"norras", "södras", "östras", "västras", "storas", "lillas", "sankt", "sankta"}
# Written regions -> today's counties (Wikidata's P131 is today's), folded,
# without "län" and a final s. Historical counties map to their successors,
# provinces to the counties they lie in; a country is no constraint.
_C = lambda *xs: set(xs)
REGION_COUNTIES = {
    "malmöhu": _C("skåne"), "kristianstad": _C("skåne"), "skåne": _C("skåne"),
    "älvsborg": _C("västra götaland"), "skaraborg": _C("västra götaland"),
    "göteborg och bohu": _C("västra götaland"), "västra götaland": _C("västra götaland"),
    "kopparberg": _C("dalarna"), "dalarna": _C("dalarna"),
    "stockholm": _C("stockholm"), "stockholms stad": _C("stockholm"), "uppsala": _C("uppsala"),
    "södermanland": _C("södermanland", "stockholm"), "östergötland": _C("östergötland"),
    "jönköping": _C("jönköping"), "kronoberg": _C("kronoberg"), "kalmar": _C("kalmar"),
    "gotland": _C("gotland"), "blekinge": _C("blekinge"), "halland": _C("halland", "västra götaland"),
    "värmland": _C("värmland"), "örebro": _C("örebro"), "västmanland": _C("västmanland", "örebro"),
    "gävleborg": _C("gävleborg"), "västernorrland": _C("västernorrland"), "jämtland": _C("jämtland"),
    "västerbotten": _C("västerbotten"), "norrbotten": _C("norrbotten"),
    # provinces
    "småland": _C("jönköping", "kronoberg", "kalmar"), "öland": _C("kalmar"),
    "västergötland": _C("västra götaland", "jönköping", "halland"), "bohuslän": _C("västra götaland"),
    "dalsland": _C("västra götaland"), "uppland": _C("uppsala", "stockholm", "västmanland"),
    "närke": _C("örebro"), "gästrikland": _C("gävleborg"), "hälsingland": _C("gävleborg", "jämtland"),
    "härjedalen": _C("jämtland"), "medelpad": _C("västernorrland"),
    "ångermanland": _C("västernorrland", "västerbotten"), "lappland": _C("norrbotten", "västerbotten"),
}


_REGION_ASCII = {}


def counties_of(region):
    """Today's counties a written region stands for, folded; empty for a
    country or a name not known as a region."""
    k = gazetteer.fold(re.sub(r"\s+län$", "", (region or "").strip(" ."), flags=re.I)).rstrip("s")
    k = re.sub(r"\s+county$", "", k)
    k = re.sub(r"\s+(?:och\s+)?", " ", k)          # "Göteborg Bohus", "Göteborgs och Bohus"
    return _REGION_ASCII.get(ascii(k).replace(" och ", " "), set())


def _fill_regions():
    for k, v in REGION_COUNTIES.items():
        _REGION_ASCII[ascii(gazetteer.fold(k)).replace(" och ", " ")] = {gazetteer.fold(x) for x in v}
    _REGION_ASCII["goteborg bohu"] = _REGION_ASCII[ascii(gazetteer.fold("göteborg och bohu")).replace(" och ", " ")]


def _county_key(c):
    return gazetteer.fold(re.sub(r"\s+län$", "", c or "")).rstrip("s")


ABBREV = {"n": "norra", "s": "södra", "ö": "östra", "o": "östra", "v": "västra", "w": "västra",
          "st": "stora", "l": "lilla"}


def ascii(key):
    """A folded key without diacritics, for names whose å/ä/ö were lost."""
    return unicodedata.normalize("NFKD", key).encode("ascii", "ignore").decode()


def degenitive(name):
    return re.sub(r"(?<=[b-df-hj-np-tv-zß])s$", "", name.strip())


def bare(name):
    """'Barkeryds socken' -> 'Barkeryds'; 'Källeryds församling (F)' -> 'Källeryds'."""
    return KIND.sub("", gazetteer.drop_county_code(name or "").strip()).strip()


def forms(name):
    """The folded keys a written parish name is looked up by."""
    b = bare(name)
    b = re.sub(r"\bS:ta\b", "Sankta", re.sub(r"\bS:t\b", "Sankt", b))
    out = {gazetteer.fold(b), gazetteer.fold(degenitive(b))}
    m = re.match(r"^(?P<abbr>[A-Za-zÅÄÖåäö:]{1,4})\.?\s+(?P<rest>\S.*)$", b)
    if m and m["abbr"].lower() in ABBREV and b[len(m["abbr"])] == ".":
        full = f"{ABBREV[m['abbr'].lower().rstrip('.')]} {m['rest']}"
        out |= {gazetteer.fold(full), gazetteer.fold(degenitive(full))}
    return {k for k in out if k}


# -- building the list ----------------------------------------------------

QUERY_NAMES = """
SELECT ?p ?t ?label (GROUP_CONCAT(DISTINCT ?alias; SEPARATOR="|") AS ?aliases)
       (SAMPLE(?code) AS ?archive) (SAMPLE(?coord) AS ?coords)
WHERE {
  VALUES ?t { wd:Q1523821 wd:Q615980 }
  ?p wdt:P31 ?t ; wdt:P17 wd:Q34 ; rdfs:label ?label . FILTER(LANG(?label) = "sv")
  OPTIONAL { ?p skos:altLabel ?alias . FILTER(LANG(?alias) = "sv") }
  OPTIONAL { ?p wdt:P5324 ?code }
  OPTIONAL { ?p wdt:P625 ?coord }
} GROUP BY ?p ?t ?label
"""
QUERY_LINKS = """
SELECT ?p (GROUP_CONCAT(DISTINCT STRAFTER(STR(?s),"entity/"); SEPARATOR="|") AS ?succ)
       (GROUP_CONCAT(DISTINCT STRAFTER(STR(?r),"entity/"); SEPARATOR="|") AS ?pred)
       (SAMPLE(?lanLabel) AS ?lan)
WHERE {
  VALUES ?t { wd:Q1523821 wd:Q615980 }
  ?p wdt:P31 ?t ; wdt:P17 wd:Q34 .
  OPTIONAL { ?p wdt:P1366 ?s }
  OPTIONAL { ?p wdt:P1365 ?r }
  OPTIONAL { ?p wdt:P131+ ?l . ?l wdt:P31 wd:Q200547 . ?l rdfs:label ?lanLabel .
             FILTER(LANG(?lanLabel)="sv") }
} GROUP BY ?p
"""


QUERY_KOMMUNER = """
SELECT DISTINCT ?label WHERE { ?k wdt:P31 wd:Q127448 ; rdfs:label ?label . FILTER(LANG(?label)="sv") }
"""


def _sparql(query):
    url = SPARQL + "?" + urllib.parse.urlencode(dict(query=query))
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/sparql-results+json"})
    rows = json.load(urllib.request.urlopen(req, timeout=300))["results"]["bindings"]
    return [{k: v["value"] for k, v in r.items()} for r in rows]


def build(path=PATH, names=None, links=None, kommuner=None):
    """Fetch (or take) the query results and write the parish list and the
    kommun names (kommuner.txt beside it)."""
    kommuner = kommuner if kommuner is not None else [r["label"] for r in _sparql(QUERY_KOMMUNER)]
    Path(path).with_name(KOMMUNER.name).write_text("\n".join(sorted(set(kommuner))) + "\n",
                                                   encoding="utf-8")
    names = names if names is not None else _sparql(QUERY_NAMES)
    links = links if links is not None else _sparql(QUERY_LINKS)
    qid = lambda u: u.rsplit("/", 1)[-1]
    link = {qid(r["p"]): r for r in links}
    out = []
    for r in names:
        q = qid(r["p"])
        lk = link.get(q, {})
        lat = lon = ""
        m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", r.get("coords", ""))
        if m:
            lon, lat = m[1], m[2]
        out.append(dict(qid=q, kind="socken" if r["t"].endswith("Q1523821") else "församling",
                        label=r["label"], aliases=r.get("aliases", ""), archive=r.get("archive", ""),
                        county=lk.get("lan", ""), lat=lat, lon=lon,
                        succ=lk.get("succ", ""), pred=lk.get("pred", "")))
    out.sort(key=lambda d: (d["label"], d["qid"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    return out


# -- the index -------------------------------------------------------------

_fill_regions()


class Names:
    def __init__(self, rows=None, path=PATH, kommuner=None):
        if kommuner is None:
            k = Path(path).with_name(KOMMUNER.name)
            kommuner = k.read_text(encoding="utf-8").split("\n") if k.exists() else []
        # modern kommun names, folded: "Aneby kommun" -> aneby
        self.kommuner = {gazetteer.fold(degenitive(re.sub(r"\s+kommun$", "", k.strip())))
                         for k in kommuner if k.strip()}
        if rows is None:
            rows = []
            if Path(path).exists():
                with open(path, encoding="utf-8") as f:
                    rows = list(csv.DictReader(f, delimiter="\t"))
        self.items = {r["qid"]: r for r in rows}
        # parish groups: a socken with the församlingar it became, and back
        parent = {q: q for q in self.items}

        def find(q):
            while parent[q] != q:
                parent[q] = parent[parent[q]]
                q = parent[q]
            return q
        for q, r in self.items.items():
            for o in (r.get("succ", "") + "|" + r.get("pred", "")).split("|"):
                if o in self.items and self._same_parish(r, self.items[o]):
                    parent[find(q)] = find(o)
        self.group = {q: find(q) for q in self.items}
        self.index = defaultdict(set)          # folded form -> qids
        self.town = {}                         # qid -> folded town its name starts with
        self.town_names = set()                # folded towns with a congregation of their own
        for q, r in self.items.items():
            names = [r["label"]] + [a for a in r.get("aliases", "").split("|") if a]
            for n in names:
                for k in forms(n):
                    self.index[k].add(q)
                if TOWN_KIND.search(n):
                    self.town_names |= forms(n)
                m = TOWN_PREFIX.match(bare(n))
                first = bare(n).split(" ", 1)
                if len(first) == 2 and first[0] not in ("Norra", "Södra", "Östra", "Västra", "Stora", "Lilla") \
                        and gazetteer.fold(first[0]) in self.kommuner and first[1][:1].isupper():
                    # "Malmö Caroli", "Lund Sankt Peters kloster": a town without the genitive
                    self.town[q] = gazetteer.fold(first[0])
                    self.town_names.add(self.town[q])
                    for k in forms(first[1]):
                        self.index[k].add(q)
                if m and m["town"].lower() not in NOT_TOWN:
                    self.town[q] = gazetteer.fold(degenitive(m["town"]))
                    self.town_names.add(self.town[q])
                    for k in forms(m["rest"]):
                        self.index[k].add(q)

    @staticmethod
    def _same_parish(a, b):
        """A socken and the församling it became share a name (one may carry
        its town); a merger into a differently named parish is not the
        same parish."""
        def keys(r):
            b = bare(r["label"])
            m = TOWN_PREFIX.match(b)
            out = {gazetteer.fold(degenitive(b))}
            if m and m["town"].lower() not in NOT_TOWN:
                out.add(gazetteer.fold(degenitive(m["rest"])))
            return out
        return bool(keys(a) & keys(b))

    def candidates(self, name, counties=(), towns=()):
        """Parish groups a written name may mean: {group qid: [qids]},
        narrowed by the counties written beside it (strictly: a namesake in
        another county is no candidate) and by towns (when that leaves any). A name a town's congregation shares without its town ("Östra
        Eneby" for "Norrköpings Östra Eneby") counts as one with it."""
        if self.is_town(name):
            return {}
        qs = set()
        for k in forms(name):
            qs |= self.index.get(k, set())
        if not qs:                     # letters lost: "Granna", "Brakne-Hoby"
            for k in forms(name):
                qs |= self.ascii_index.get(ascii(k), set())
        groups = defaultdict(list)
        for q in qs:
            groups[self.group[q]].append(q)
        allowed = set().union(*(counties_of(c) for c in counties)) if counties else set()
        if allowed:                   # a county written beside it rules others out
            keep = {g: v for g, v in groups.items()
                    if any(_county_key(self.items[q]["county"]) in allowed for q in v)}
            if not keep:              # only items without a county on Wikidata left
                keep = {g: v for g, v in groups.items() if not any(self.items[q]["county"] for q in v)}
            groups = keep
        if len(groups) > 1 and towns:
            ts = {gazetteer.fold(degenitive(t)) for t in towns}
            keep = {g: v for g, v in groups.items() if any(self.town.get(q) in ts for q in v)}
            groups = keep or groups
        return dict(groups)

    @property
    def ascii_index(self):
        if not hasattr(self, "_ascii"):
            self._ascii = defaultdict(set)
            for k, qs in self.index.items():
                self._ascii[ascii(k)] |= qs
        return self._ascii

    def is_town(self, name):
        """A town's name written alone ("Ystad", "Norrköping"): the town,
        not one of its congregations. Written as a parish ("Ystads
        stadsförsamling") it is not."""
        n = gazetteer.drop_county_code(name or "").strip()
        if KIND.search(n):
            return False
        return bool(forms(n) & self.town_names) or \
            bool({ascii(k) for k in forms(n)} & {ascii(t) for t in self.town_names})

    def is_kommun(self, name):
        """A modern kommun's name ("Aneby", "Tranås kommun")."""
        n = re.sub(r"\s+kommun$", "", (name or "").strip(), flags=re.I)
        return bool({gazetteer.fold(n), gazetteer.fold(degenitive(n))} & self.kommuner)

    def label(self, group):
        """A readable name for a parish group: its församling's name without
        its kind or genitive ("Gärdhem"), else its socken's."""
        qs = [q for q, g in self.group.items() if g == group]
        qs.sort(key=lambda q: (self.items[q]["kind"] != "församling", self.items[q]["label"]))
        return degenitive(bare(self.items[qs[0]]["label"])) if qs else ""

    def coords(self, name):
        """(lat, lon, "parish", source) for a parish name that names one
        parish group, from its församling's point (else its socken's)."""
        groups = self.candidates(name)
        if len(groups) != 1:
            return None
        qs = sorted(self.members(next(iter(groups))),
                    key=lambda q: self.items[q]["kind"] != "församling")
        q = next((q for q in qs if self.items[q].get("lat")), None)
        return (float(self.items[q]["lat"]), float(self.items[q]["lon"]), "parish",
                "wikidata parish list") if q else None

    def members(self, group):
        return [q for q, g in self.group.items() if g == group]

    def towns(self):
        """Folded names of towns that have congregations of their own."""
        return set(self.town_names)


_DEFAULT = None


def load():
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Names()
    return _DEFAULT


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        rows = build()
        print(f"wrote {len(rows)} parishes to {PATH}")
    else:
        n = load()
        for name in sys.argv[1:]:
            for g, qs in n.candidates(name).items():
                print(name, "->", n.label(g), [f"{q} {n.items[q]['label']} ({n.items[q]['county']})" for q in qs])
