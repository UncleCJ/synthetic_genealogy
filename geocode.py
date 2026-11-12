"""
Coordinates for the gazetteer's places, at whatever precision the sources
allow, each recorded with its level and source:

    level    source                                   rough uncertainty
    farm     TORA (Riksarkivet's historical           ~0.3 km
             settlements), OpenStreetMap dwelling,
             farm or hamlet
    village  TORA / OpenStreetMap village             ~1 km
    parent   the place it lies `within` (a croft      ~2 km
             without its own point)
    parish   the parish's Wikidata coordinates        ~6 km
    town     OpenStreetMap town or city (places       ~5 km
             outside the gazetteer)
    region   county, state or country                 ~50-300 km

A candidate must lie within MAX_KM of the parish's own coordinates;
same-named farms are common ("Rysseryd" is in Linderås and in Bellö).

Sources and etiquette:
- TORA: SPARQL at tora.entryscape.net/store/sparql; label, WGS84
  lat/long, coordinate accuracy, modern parish. Covers ~27,000 older
  settlements (Det medeltida Sverige), few crofts.
- OpenStreetMap Nominatim: one request a second, identified, cached, and
  searched inside a box around the parish (usage policy).

Coordinates go into gazetteer/places.toml (public) as lat, lon, geo_level,
geo_source; a place marked `checked`, or with geo_source = "manual", is
never overwritten. Lookups for place strings outside the gazetteer
(towns abroad, modern addresses reduced to their town) are cached
privately in data/, and street names and numbers are never sent.

Sketch status: run on one tree. Not handled: historical maps
(Lantmäteriet's ekonomiska kartan), farms renamed since.

    python geocode.py places          # fill gazetteer coordinates
    python geocode.py show Mjölarp
"""
import difflib
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import gazetteer as gz
import textfix

TORA = "https://tora.entryscape.net/store/sparql"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "synthetic-genealogy/0.1 (geocode.py; research sketch)"
MAX_KM = 12
LEVEL_KM = {"farm": 0.3, "village": 1, "parent": 2, "parish": 6, "town": 5,
            "region": 60, "country": 300}
OSM_LEVEL = {"isolated_dwelling": "farm", "farm": "farm", "hamlet": "farm",
             "locality": "farm", "neighbourhood": "village", "village": "village",
             "suburb": "village", "quarter": "village", "town": "town", "city": "town",
             "municipality": "town", "county": "region", "state": "region",
             "country": "country"}


def km(a, b):
    """Great-circle distance between (lat, lon) pairs."""
    (la1, lo1), (la2, lo2) = [(math.radians(x), math.radians(y)) for x, y in (a, b)]
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


class Cache:
    def __init__(self, path):
        self.path = Path(path)
        self.d = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.d, ensure_ascii=False, indent=0, sort_keys=True),
                             encoding="utf-8")


def _get(url, params, accept=None):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": UA, **({"Accept": accept} if accept else {})})
    for attempt in range(4):
        try:
            return urllib.request.urlopen(req, timeout=90).read().decode("utf-8")
        except OSError:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"unreachable: {url}")


# -- TORA ------------------------------------------------------------------------------

def tora(cache, names):
    """name -> [dict(id, lat, lon, accuracy, parish)] for each name, in
    batches (one SPARQL query per 40 names). Exact label match."""
    todo = sorted({n for n in names if f"tora:{n}" not in cache.d})
    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        values = " ".join(json.dumps(n) for n in batch)
        q = ("PREFIX skos: <http://www.w3.org/2004/02/skos/core#> "
             "PREFIX geo: <http://www.w3.org/2003/01/geo/wgs84_pos#> "
             "PREFIX dct: <http://purl.org/dc/terms/> "
             "SELECT DISTINCT ?l ?s ?lat ?long ?acc ?pl WHERE { VALUES ?l { " + values + " } "
             "?s skos:prefLabel ?l ; geo:lat ?lat ; geo:long ?long . "
             "OPTIONAL { ?s dct:coverage ?acc } "
             "OPTIONAL { ?s dct:isPartOf ?par . ?par skos:prefLabel ?pl } }")
        xml = _get(TORA, dict(query=q, output="json"))
        found = {n: {} for n in batch}
        for r in re.findall(r"<result>(.*?)</result>", xml, re.S):
            b = dict(re.findall(r"<binding name='(\w+)'>\s*<(?:uri|literal)[^>]*>([^<]*)<", r))
            n = b.get("l")
            if n not in found:
                continue
            tid = b["s"].rsplit("/", 1)[-1]
            e = found[n].setdefault(tid, dict(id=tid, lat=float(b["lat"].replace(",", ".")),
                                              lon=float(b["long"].replace(",", ".")),
                                              accuracy=b.get("acc", "").rsplit("/", 1)[-1],
                                              parish=[]))
            if b.get("pl"):
                p = re.sub(r"\s+(socken|församling)$", "", b["pl"])
                if p not in e["parish"]:
                    e["parish"].append(p)
        for n in batch:
            cache.d[f"tora:{n}"] = list(found[n].values())
        time.sleep(1)
    return {n: cache.d.get(f"tora:{n}", []) for n in names}


# -- Nominatim --------------------------------------------------------------------------

_last = [0.0]
OFFLINE = [False]          # set True to use cached answers only


def nominatim(cache, q, around=None, box_km=15, country="se"):
    """OpenStreetMap search; inside a box around (lat, lon) when given."""
    key = f"osm:{q}|{country}|{around and (round(around[0], 2), round(around[1], 2))}"
    if key in cache.d or OFFLINE[0]:
        return cache.d.get(key, [])
    params = dict(q=q, format="jsonv2", limit=5)
    if country:
        params["countrycodes"] = country
    if around:
        dlat = box_km / 111
        dlon = box_km / (111 * math.cos(math.radians(around[0])))
        params.update(viewbox=f"{around[1] - dlon},{around[0] + dlat},{around[1] + dlon},{around[0] - dlat}",
                      bounded=1)
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    out = json.loads(_get(NOMINATIM, params))
    _last[0] = time.time()
    cache.d[key] = [dict(name=x.get("name", ""), type=x.get("addresstype") or x.get("type"),
                         lat=float(x["lat"]), lon=float(x["lon"]),
                         osm=f"{x.get('osm_type')}/{x.get('osm_id')}") for x in out]
    return cache.d[key]


# -- gazetteer places --------------------------------------------------------------------

def _names(p):
    """Names to try for a place: its display name, then variants; for a
    'X Y' name also its last word (the farm in 'Uppgrenna Bultagård' is
    under the village Uppgrenna, so try the village too)."""
    out = [p.get("name", "")] + [gz.parse(v)[-1][0] for v in p.get("variants", [])]
    # "Rysseryd eller Falarp", "Duve Eller Dårebo": two names for one place
    out += [x.strip(" .") for n in list(out) for x in re.split(r"\s+eller\.?\s+", n, flags=re.I)
            if re.search(r"\beller\b", n, re.I)]
    words = p.get("name", "").split()
    if len(words) > 1:
        out.append(words[0])
    seen, res = set(), []
    for n in out:
        n = re.sub(r"\s*\(.*?\)", "", n).strip()
        if n and gz.fold(n) not in seen and not n.lower().endswith(" rote"):
            seen.add(gz.fold(n))
            res.append(n)
    return res


def fill_places(g, cache, network=True):
    """Coordinates for gazetteer places: TORA, then OpenStreetMap, then the
    place it lies within, each checked against the parish; else nothing
    (the parish's own point is used at display time)."""
    centre = {n: (p["lat"], p["lon"]) for n, p in g.parishes.items() if p.get("lat")}
    places = [(pid, p) for pid, p in g.places.items()
              if not p.get("checked") and p.get("geo_source") != "manual"]
    if network:
        tora(cache, {n for _, p in places for n in _names(p)})
    stats = {}
    for pid, p in sorted(places):
        par = p.get("parish")
        if gz.generic(p.get("name")):
            for f in ("lat", "lon", "geo_level", "geo_source"):    # "Sörgården": no point of its own
                p.pop(f, None)
            continue
        c = centre.get(par)
        hit = None
        for i, n in enumerate(_names(p)):
            whole = i == 0 or n in [gz.parse(v)[-1][0] for v in p.get("variants", [])]
            for t in cache.d.get(f"tora:{n}", []):
                same = par in t["parish"] or (c and km(c, (t["lat"], t["lon"])) <= MAX_KM)
                if same:
                    hit = (t["lat"], t["lon"], "farm" if whole else "village", f"tora:{t['id']}")
                    break
            if hit:
                break
            if c and network:
                for o in nominatim(cache, n, around=c):
                    if gz.fold(o["name"]) == gz.fold(n) and km(c, (o["lat"], o["lon"])) <= MAX_KM:
                        lvl = OSM_LEVEL.get(o["type"], "farm")
                        hit = (o["lat"], o["lon"], lvl if whole else "village", f"osm:{o['osm']}")
                        break
            if hit:
                break
        if hit:
            p.update(lat=round(hit[0], 5), lon=round(hit[1], 5), geo_level=hit[2], geo_source=hit[3])
        stats[hit[3].split(":")[0] if hit else "none"] = stats.get(hit[3].split(":")[0] if hit else "none", 0) + 1
    # crofts and farms without a point take the place they lie within
    for pid, p in g.places.items():
        if not p.get("lat") and p.get("within") in g.places and g.places[p["within"]].get("lat"):
            w = g.places[p["within"]]
            p.update(lat=w["lat"], lon=w["lon"], geo_level="parent", geo_source=f"within:{p['within']}")
            stats["parent"] = stats.get("parent", 0) + 1
    return stats


# -- any place string (life paths) ----------------------------------------------------------

_STREET = re.compile(r"\d|gatan\b|vägen\b|gränd\b|kvarteret|\bkv\.|\bnr\b|street|\bst\.|road|avenue|\bave\b",
                     re.I)
# Short forms of a country that the gazetteer's list leaves out ("Swdn").
_COUNTRY_ABBR = {"swdn": "se", "swed": "se", "sw": "se", "sv": "se", "nor": "no", "dan": "dk"}
# Danish and Norwegian kinds after a name: "Føns By og Sogn", "Odense Amt".
_DANO_NORWEGIAN_KIND = re.compile(r"\s+(?:by\s+og\s+)?(?:sogn|amt|herred|fylke|kommune|kirkegård|kirkegaard)$",
                                  re.I)


def _letters(s):
    """Loose letters-only key: Sturkoe = Sturkö, Gränna = Granna."""
    s = gz.fold(s)
    for a, b in (("oe", "o"), ("ae", "a"), ("aa", "a"), ("ö", "o"), ("ä", "a"), ("å", "a"),
                 ("é", "e"), ("ü", "u")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z]", "", s)


def _swedish(s):
    """Undo the spelling records abroad use for å/ä/ö: Sturkoe, Jaerna, Aamaal."""
    for a, b in (("oe", "ö"), ("ae", "ä"), ("aa", "å"), ("Oe", "Ö"), ("Ae", "Ä"), ("Aa", "Å")):
        s = s.replace(a, b)
    return s


def _name_fits(found, asked):
    """A hit counts only if its name is one of the words asked for
    (Nominatim matches loosely: "W. Ryr" finds Deir Jarir in Palestine)."""
    f = _letters(found)
    words = [_letters(w) for w in re.split(r"[\s/]+", asked) if len(_letters(w)) >= 3]
    return bool(f) and any(f == w or (len(w) >= 4 and (f.startswith(w) or w.startswith(f)))
                           or w in f.split() for w in words + [_letters(asked)])


def locality(private_cache, plac):
    """(lat, lon, level, source, name) for a place string outside the
    gazetteer, at town level at best; name is OpenStreetMap's spelling.
    Parts with digits or street words are dropped before anything is sent.
    The country is the gazetteer's reading (gazetteer.country): without
    one the search stays in Sweden; a US state means the USA, misspelt
    ones included ("Conneticut"); Danish and Norwegian kinds are dropped
    ("Føns Sogn" -> Føns, "Vestergade i Hasle" -> Hasle). A hit must carry
    one of the names asked for. When no part is found, the country alone
    ("USA", "Norge", "Nordamerika"), at level country."""
    parts = [re.sub(r"\([^()]*\)|\?", " ", p).strip()
             for p in re.split(r"[,;]", textfix.fix(plac or ""))]
    parts = [p for p in parts if p]
    if not parts:
        return None
    country = gz.country(parts) or "se"
    words = parts[-1].split()                  # "Chicago Nord Amerika": the country's words off
    for i in range(len(words)):                # the longest reading: "Nord Amerika" is a country
        if gz.country_code(" ".join(words[i:])):
            parts[-1] = " ".join(words[:i])
            break
    core = []
    for i, p in enumerate(parts):
        k = p.lower().strip(". ")
        if gz.country_code(p) or k in _COUNTRY_ABBR:
            continue
        if country == "us":
            st = gz.us_state(p) or (i and next(iter(difflib.get_close_matches(
                p.title(), gz.US_STATES.values(), n=1, cutoff=0.85)), ""))
            if st:
                core.append(st)
                continue
        if country in ("dk", "no", "dk,no"):
            p = _DANO_NORWEGIAN_KIND.sub("", re.sub(r"^.*\s+i\s+", "", p)).strip(' "')
        p = gz.modern_town(p)
        if p and not _STREET.search(p):
            core.append(p)
    for i in range(len(core)):
        q = ", ".join(dict.fromkeys(core[i:i + 3]))
        if not q:
            continue
        hits = nominatim(private_cache, q, country=country)
        sv = _swedish(q) if country == "se" else q
        if not any(_name_fits(o.get("name", ""), core[i]) for o in hits) and sv != q:
            hits = nominatim(private_cache, sv, country=country)     # "Sturkoe" -> "Sturkö"
        for o in hits:
            lvl = OSM_LEVEL.get(o["type"])
            if lvl and _name_fits(o.get("name", ""), core[i]):
                # the map's own spelling: "Sturkoe" in a record is Sturkö
                return (o["lat"], o["lon"], "town" if lvl in ("farm", "village") else lvl,
                        f"osm:{o['osm']}", o.get("name") or core[i])
    if country != "se" and country in gz.COUNTRY_NAMES:
        for o in nominatim(private_cache, gz.COUNTRY_NAMES[country][0], country=country):
            if o["type"] == "country":
                return o["lat"], o["lon"], "country", f"osm:{o['osm']}", o.get("name") or gz.COUNTRY_NAMES[country][0]
    return None


def _main(argv):
    g = gz.Gazetteer()
    cache = Cache(gz.CACHE / "geocode.json")
    cmd = argv[0] if argv else "places"
    try:
        if cmd == "places":
            stats = fill_places(g, cache, network="--offline" not in argv)
            g.save()
            have = sum(1 for p in g.places.values() if p.get("lat"))
            print(f"{have} of {len(g.places)} places have coordinates; this run: {stats}")
        elif cmd == "show":
            rx = re.compile(" ".join(argv[1:]), re.I)
            for pid, p in sorted(g.places.items()):
                if rx.search(pid):
                    print(pid, p.get("lat"), p.get("lon"), p.get("geo_level"), p.get("geo_source"))
        else:
            print(__doc__)
    finally:
        cache.save()


if __name__ == "__main__":
    _main(sys.argv[1:])
