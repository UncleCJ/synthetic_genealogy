"""
Places as entities: resolve the place evidence in a GEDCOM to Wikidata
parish items and read each parish's history.

Evidence, strongest first: a Riksarkivet citation (its reference code is
the parish archive, Wikidata P5324, so the match is exact); a vendor's
volume label (names the parish and the series and volume, by name only);
a free-text PLAC (ambiguous names, so only candidates). How Wikidata models
a parish over time (socken, församling, distrikt): docs/records.md,
"Parishes, congregations and towns".

Sketch status (unvalidated): run on one Gramps export. A code can sit on
several items, so it returns a list. Not handled: county, härad and diocese
at an event's date, farm-level places, TORA lookups. Wikidata answers are
cached in gazetteer/cache/wikidata.json (public); the action API and its
`haswbstatement` search are used because WDQS is often rate-limited.

    python places.py codes             # archive codes cited in the tree
    python places.py volumes           # vendor volume labels cited
    python places.py history Q10717331 # one parish's chain of successors
    python places.py name "Norra Ryr"  # candidate parishes for a name
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, deque
from pathlib import Path

import references

API = "https://www.wikidata.org/w/api.php"
UA = "synthetic-genealogy/0.1 (places.py; research sketch)"

SOCKEN, FORSAMLING, DISTRIKT = "Q1523821", "Q615980", "Q18333556"
PARISH_TYPES = {SOCKEN: "socken", FORSAMLING: "församling", DISTRIKT: "distrikt"}

# Riksarkivet citation: archive, series, code[/subseries/volume] (years),
# bildid, page. Subseries can contain spaces ("A II a").
RA_CITATION = references.RA_CITATION        # the reader lives in references.py

# MyHeritage household examinations: "Bok:Lane-Ryr AI7, 1861 - 1867",
# "BokVäne-Ryr AIIa 1, 1895 - 1920" (the colon is sometimes lost).
MH_VOLUME = re.compile(
    r"Bok:?\s*(?P<parish>[^\n,]+?)\s+(?P<series>A\s?I{1,2}\s?a?)\s?(?P<vol>\d+)"
    r"\s*,\s*(?P<years>\d{4}\s*-\s*\d{4})")

# Abbreviations seen in transcribed place names. Heuristic: "W." can also
# stand for Västra, so treat expansions as candidates, never as answers.
ABBREV = [(r"^N\.?\s+", ["Norra "]), (r"^S\.?\s+", ["Södra "]),
          (r"^V\.?\s+", ["Västra "]), (r"^Ö\.?\s+", ["Östra "]),
          (r"^W\.?\s+", ["Väne-", "Västra "])]


# -- Wikidata client with cache -------------------------------------------

class Wikidata:
    def __init__(self, cache=None):
        self.cache_path = Path(cache) if cache else None
        self.cache = {}
        if self.cache_path and self.cache_path.exists():
            self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))

    def save(self):
        if self.cache_path:
            self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False),
                                       encoding="utf-8")

    def api(self, **params):
        params["format"] = "json"
        url = API + "?" + urllib.parse.urlencode(sorted(params.items()))
        if url in self.cache:
            return self.cache[url]
        for attempt in range(6):
            time.sleep(1.0)                      # be polite; the API throttles
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                data = json.load(urllib.request.urlopen(req, timeout=60))
                break
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    raise
                time.sleep(int(e.headers.get("Retry-After") or 10 * (attempt + 1)))
        else:
            raise RuntimeError("Wikidata keeps rate-limiting; try later")
        self.cache[url] = data
        return data

    def search(self, query, limit=20):
        r = self.api(action="query", list="search", srsearch=query, srlimit=limit)
        return [h["title"] for h in r["query"]["search"]]

    def entities(self, ids):
        out, ids = {}, sorted(set(ids))
        for i in range(0, len(ids), 50):
            r = self.api(action="wbgetentities", ids="|".join(ids[i:i + 50]),
                         props="labels|aliases|descriptions|claims", languages="sv|en")
            out.update(r["entities"])
        return out

    def entity(self, qid):
        return self.entities([qid])[qid]

    def label(self, qid):
        return _label(self.entity(qid))


def _label(e):
    L = e.get("labels", {})
    return (L.get("sv") or L.get("en") or {}).get("value", e.get("id", "?"))


def _value(snak):
    v = snak.get("datavalue", {}).get("value")
    if isinstance(v, dict):
        if "id" in v:
            return v["id"]
        if "time" in v:
            y = re.match(r"[+-](\d+)", v["time"])
            return int(y[1]) if y else None
    return v


def _claims(e, prop):
    """[(value, {qualifier prop: [values]}, rank)] skipping deprecated."""
    out = []
    for c in e.get("claims", {}).get(prop, []):
        if c.get("rank") == "deprecated":
            continue
        q = {k: [_value(s) for s in v] for k, v in c.get("qualifiers", {}).items()}
        out.append((_value(c["mainsnak"]), q, c.get("rank")))
    return out


def _one(q, prop):
    v = q.get(prop)
    return v[0] if v else None


# -- parish records --------------------------------------------------------

def parish(wd, qid):
    """The dated facts this module uses, from one item."""
    e = wd.entity(qid)
    types = [v for v, _, _ in _claims(e, "P31")]
    succ = lambda p: [dict(item=v, applies_to=_one(q, "P518"),
                           year=_one(q, "P585") or _one(q, "P580"))
                      for v, q, _ in _claims(e, p)]
    return dict(
        id=qid, label=_label(e),
        aliases=[a["value"] for a in e.get("aliases", {}).get("sv", [])],
        kind=next((PARISH_TYPES[t] for t in types if t in PARISH_TYPES), None),
        archive=[v for v, _, _ in _claims(e, "P5324") if v],   # skip "no value"
        ra_id=[v for v, _, _ in _claims(e, "P14316") if v],
        ata=[v for v, _, _ in _claims(e, "P777") if v],
        codes=[(v, _one(q, "P580"), _one(q, "P582")) for v, q, _ in _claims(e, "P778") if v],
        located=[(v, _one(q, "P580"), _one(q, "P582")) for v, q, _ in _claims(e, "P131") if v],
        founded=next((v for v, _, _ in _claims(e, "P571") if v), None),
        dissolved=next((v for v, _, _ in _claims(e, "P576") if v), None),
        replaces=succ("P1365"), replaced_by=succ("P1366"))


def code_at(p, year):
    """The parish code (P778) valid in `year`, or None."""
    for code, start, end in p["codes"]:
        if (start is None or start <= year) and (end is None or year <= end):
            return code


def history(wd, qid, depth=3, limit=30):
    """Parishes linked to qid by replaces / replaced-by, up to `depth`
    links away, in order of their earliest known year. Non-parish
    successors (a landskommun) are listed but not followed. Without these
    limits the walk runs on through later mergers into every parish of
    today's municipality."""
    seen, todo = {}, deque([(qid, 0)])
    while todo and len(seen) < limit:
        q, d = todo.popleft()
        if q in seen:
            continue
        seen[q] = parish(wd, q)
        if d >= depth or (seen[q]["kind"] is None and q != qid):
            continue
        for link in seen[q]["replaces"] + seen[q]["replaced_by"]:
            if link["item"] and link["item"] not in seen:
                todo.append((link["item"], d + 1))
    def start(p):
        years = [p["founded"]] + [l["year"] for l in p["replaces"]]
        years += [min(l["year"] for l in p["replaced_by"] if l["year"])] \
            if p["kind"] == "socken" and any(l["year"] for l in p["replaced_by"]) else []
        years = [y for y in years if y]
        return min(years) if years else (0 if p["kind"] == "socken" else 9999)
    return sorted(seen.values(), key=start)


def items_for_code(wd, code):
    """Items holding archive code `code` (P5324), usually church parishes."""
    return wd.search(f'haswbstatement:"P5324={code}"')


def expand(name):
    """Spelling candidates for an abbreviated place name."""
    name = name.strip()
    out = [name]
    for pat, subs in ABBREV:
        if re.match(pat, name):
            out += [re.sub(pat, s, name) for s in subs]
    # old orthography: W for V, e.g. "Wäne"
    out += [n.replace("W", "V").replace("w", "v") for n in out if "W" in n or "w" in n]
    return list(dict.fromkeys(out))


def candidates(wd, name):
    """Parish items (socken, församling, distrikt) whose label or alias
    contains `name` or one of its expansions."""
    hits = []
    for n in expand(name):
        base = re.sub(r"\s+(socken|församling|distrikt)$", "", n)
        for q in ("socken", "församling", "distrikt"):
            hits += wd.search(f'"{base}" {q}', limit=10)
    out = []
    E = wd.entities(hits) if hits else {}
    for qid, e in E.items():
        names = [_label(e)] + [a["value"] for a in e.get("aliases", {}).get("sv", [])]
        types = {v for v, _, _ in _claims(e, "P31")}
        if types & PARISH_TYPES.keys() and any(
                re.sub(r"\s+(socken|församling|distrikt)$", "", b).lower()
                in n.lower() for n in names for b in expand(name)):
            out.append(parish(wd, qid))
    if not out and " " in name.strip():
        # e.g. "Norra Ryr" is no Wikidata alias: fall back to every parish
        # whose name ends in the last word ("Väne-Ryr", "Lane-Ryr", ...).
        last = name.split()[-1]
        out = [p for p in candidates(wd, last)
               if re.search(rf"(^|-){re.escape(last)}s?\b", p["label"], re.I)]
    return out


# -- evidence in a GEDCOM ----------------------------------------------------

def _texts(nodes):
    for n in nodes:
        if n["value"]:
            yield n["value"]
        yield from _texts(n["sub"])


def citations(records):
    """Riksarkivet citations in any text value, one dict per occurrence."""
    for t in _texts(records):
        t = re.sub(r"<[^>]+>", " ", t)            # Gramps keeps HTML in notes
        for m in RA_CITATION.finditer(t):
            yield {k: (v.strip() if v else v) for k, v in m.groupdict().items()}


def volumes(records):
    """Vendor volume labels (MyHeritage household examinations)."""
    for t in _texts(records):
        for m in MH_VOLUME.finditer(t):
            d = {k: v.strip() for k, v in m.groupdict().items()}
            d["series"] = " ".join(re.findall(r"A|II|I|a", d["series"].replace(" ", "")))
            yield d


# -- command line ------------------------------------------------------------

def _years(a, b):
    return f"{a or ''}–{b or ''}" if (a or b) else ""


def _print_parish(wd, p, indent="  "):
    print(f"{indent}{p['id']} {p['label']} [{p['kind'] or '?'}]"
          + (f" aka {', '.join(p['aliases'])}" if p["aliases"] else ""))
    if p["archive"]:
        print(f"{indent}  archive {', '.join(p['archive'])}")
    if p["ata"]:
        print(f"{indent}  ATA {', '.join(p['ata'])}")
    for c, a, b in p["codes"]:
        print(f"{indent}  code {c} {_years(a, b)}")
    if p["founded"] or p["dissolved"]:
        print(f"{indent}  exists {_years(p['founded'], p['dissolved'])}")
    for l in p["replaced_by"]:
        part = f" ({wd.label(l['applies_to'])})" if l["applies_to"] else ""
        print(f"{indent}  -> {l['item']} {wd.label(l['item'])}{part} {l['year'] or ''}")


def _main(argv):
    import config
    cfg = config.load()
    wd = Wikidata(Path(__file__).parent / "gazetteer" / "cache" / "wikidata.json")
    cmd, args = (argv[0], argv[1:]) if argv else ("codes", [])
    try:
        if cmd in ("codes", "volumes"):
            import gedcom_io
            g = cfg.get("gedcom") or {}
            records = gedcom_io.parse(config.path(cfg, g["file"]), **gedcom_io.options(cfg))
        if cmd == "codes":
            cites = list(citations(records))
            by_code = Counter(c["code"] for c in cites)
            names = {c["code"]: c["archive"] for c in cites}
            print(f"{len(cites)} citations, {len(by_code)} archive codes")
            for code, n in sorted(by_code.items()):
                items = items_for_code(wd, code)
                labels = "; ".join(f"{q} {wd.label(q)}" for q in items) or "no item"
                print(f"{code:16} {n:4}  {names[code]:40} -> {labels}")
        elif cmd == "volumes":
            vols = Counter((v["parish"], v["series"], v["vol"], v["years"])
                           for v in volumes(records))
            for (par, ser, vol, yrs), n in sorted(vols.items()):
                print(f"{par:20} {ser} {vol:>3} {yrs:12} x{n}")
        elif cmd == "history":
            for p in history(wd, args[0]):
                _print_parish(wd, p)
        elif cmd == "name":
            for p in candidates(wd, " ".join(args)):
                _print_parish(wd, p)
        else:
            print(__doc__)
    finally:
        wd.save()


if __name__ == "__main__":
    _main(sys.argv[1:])
