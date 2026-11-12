"""Place strings shown with their whole hierarchy, for every view.

A tree writes one place many ways: "Dädesjö, Uppvidinge", "Uppvidinge,
Kronobergs län", "Adelöv (F), Småland, Sverige". Each string is read into
levels (farm and other detail as written, parish, town or kommun,
landskap, län, country) and the levels a string leaves out are filled
from what the other strings of the tree say, so the first is shown as
"Dädesjö, Uppvidinge, Småland, Kronobergs län":

- learnt: every string that names a parish, town, län or landskap votes
  for the broader levels written beside it; a level is filled when at
  least two thirds of the votes agree ("Dädesjö, Uppvidinge" twice,
  "Dädesjö, Växjö" once gives Uppvidinge);
- known: a county letter ("Adelöv (F)") names its län; the parish list
  (parish_names) gives a parish's län when the name is unique there
  (today's län, from Wikidata); a län that lies in one landskap gives it.

Sweden is left out; another country is kept, last. A string outside
Sweden (gazetteer.abroad) is shown as written, with its country added
when only a state or Dano-Norwegian words say it ("Omaha, Douglas, NE,
USA"), and votes for nothing. What is written is never replaced, only
completed. Unvalidated: votes come from the tree's
own strings, so a misreading repeated often enough wins.

    h = Hierarchy(place strings, or (place string, parish) pairs)
    h.label("Dädesjö, Uppvidinge")   # "Dädesjö, Uppvidinge, Småland, Kronobergs län"
"""
import re
from collections import Counter, defaultdict

import gazetteer
import parish_names

LEVELS = ("parish", "town", "landskap", "lan", "country")   # most specific first, after the detail
# Län letters as parish names carry them ("Källeryd (F)"), the pre-1997 set.
LAN_CODES = gazetteer.LAN_CODES
LAN_NAMES = sorted(set(LAN_CODES.values()) | {"Skåne län", "Västra Götalands län", "Dalarnas län",
                                              "Stora Kopparbergs län"})
LANDSKAP = ["Skåne", "Blekinge", "Halland", "Småland", "Öland", "Gotland", "Västergötland",
            "Bohuslän", "Dalsland", "Östergötland", "Södermanland", "Närke", "Värmland", "Uppland",
            "Västmanland", "Dalarna", "Gästrikland", "Hälsingland", "Härjedalen", "Jämtland",
            "Medelpad", "Ångermanland", "Västerbotten", "Norrbotten", "Lappland"]
# Län that lie in one landskap (as they were drawn before 1997).
LAN_LANDSKAP = {
    "Stockholms stad": "Uppland", "Uppsala län": "Uppland", "Södermanlands län": "Södermanland",
    "Östergötlands län": "Östergötland", "Jönköpings län": "Småland", "Kronobergs län": "Småland",
    "Gotlands län": "Gotland", "Blekinge län": "Blekinge", "Kristianstads län": "Skåne",
    "Malmöhus län": "Skåne", "Skåne län": "Skåne", "Hallands län": "Halland",
    "Skaraborgs län": "Västergötland", "Värmlands län": "Värmland", "Västmanlands län": "Västmanland",
    "Kopparbergs län": "Dalarna", "Stora Kopparbergs län": "Dalarna", "Dalarnas län": "Dalarna",
}
LAN_SUFFIX = re.compile(r"(?:\s+|-)(?:län|lan|len|county)\.?$", re.I)
STIFT = re.compile(r"\s+(?:stift|kontrakt|härad|domsaga|tingslag)$", re.I)
KOMMUN = re.compile(r"\s+kommun$", re.I)
PARISH_KIND = re.compile(r"\s+(?:socken|sn\.?|församling|förs\.?)$", re.I)
TRAILING_LAN = re.compile(r"^(.*?\S)\s+((?:[A-ZÅÄÖ][\wåäö]*\s+){1,3}(?:län|lan|len))$", re.I)
CODE = re.compile(r"\s*\((?P<c>[A-ZÅÄÖ]{1,2})\)\s*$")


# Which levels vote for which: a parish for its town, landskap and län, a
# town for its län. Not a town for its landskap (Stockholm lies in two),
# nor a län for its landskap or back (Stockholms län: Uppland and
# Södermanland); those come from LAN_LANDSKAP alone.
VOTES = {"parish": ("town", "landskap", "lan"), "town": ("lan",)}


def _key(s):
    return parish_names.ascii(gazetteer.fold(s or ""))


def _lan_key(s):
    k = _key(LAN_SUFFIX.sub("", s.strip(" .")))
    return " ".join(w.rstrip("s") for w in k.replace(" och ", " ").split())


_LAN = {_lan_key(n): n for n in LAN_NAMES}
_LAN["stora kopparberg"] = "Kopparbergs län"
_LANDSKAP = {_key(n): n for n in LANDSKAP}


def lan_of(part):
    """The län a written part names ("Kronobergs Len", "AB-län",
    "Stockholms Län"), or None. Only a part with "län" (or "county")
    says so: "Kalmar" alone is a town."""
    if not LAN_SUFFIX.search(part or ""):
        return None
    k = LAN_SUFFIX.sub("", part.strip(" .")).strip()
    if k.upper() in LAN_CODES:
        return LAN_CODES[k.upper()]
    return _LAN.get(_lan_key(part), part.strip(" ."))


def landskap_of(part):
    return _LANDSKAP.get(_key((part or "").strip(" .")))


def kommun_display(part):
    """"Gislaveds kommun" -> "Gislaved"; "Bengtsfors kommun" keeps its s."""
    p = part.strip()
    if not KOMMUN.search(p):
        return p
    p = KOMMUN.sub("", p).strip()
    return p if re.search(r"(?:fors|grums)$", p, re.I) else parish_names.degenitive(p)


def parish_display(part):
    """A parish as written, without its county letter and plain kind:
    "Dädesjö socken" -> "Dädesjö"; "Linköpings domkyrkoförsamling" stays."""
    p = CODE.sub("", part).strip()
    q = PARISH_KIND.sub("", p)
    return parish_names.degenitive(q) if q != p else p


class Hierarchy:
    def __init__(self, places=(), names=None):
        self.names = names if names is not None else parish_names.load()
        self._cand = {}
        self._parsed = {}
        # votes[(level, key)][level above] = Counter(display)
        self.votes = defaultdict(lambda: defaultdict(Counter))
        for item in places:
            plac, parish = item if isinstance(item, tuple) else (item, None)
            r = self.parse(plac, parish)
            if r.get("abroad"):
                continue
            for lv, above in VOTES.items():
                if r[lv]:
                    for lv2 in above:
                        if r[lv2]:
                            self.votes[(lv, _key(r[lv]))][lv2][r[lv2]] += 1

    # -- reading one string ------------------------------------------------------

    def _candidates(self, part, regions):
        k = (part, tuple(regions))
        if k not in self._cand:
            self._cand[k] = self.names.candidates(part, counties=regions)
        return self._cand[k]

    def _towns_of(self, parish, regions):
        """Towns a parish's congregations are named after ("Stockholms
        Katarina" -> stockholm), folded."""
        return {self.names.town.get(q) for v in self._candidates(parish, regions).values() for q in v} - {None}

    def _townish(self, part):
        return bool(KOMMUN.search(part)) or ((self.names.is_kommun(part) or self.names.is_town(part))
                                             and not CODE.search(part) and not PARISH_KIND.search(part))

    def parse(self, plac, parish=None):
        k = (plac, parish)
        if k not in self._parsed:
            self._parsed[k] = self._parse(plac, parish)
        return dict(self._parsed[k], detail=list(self._parsed[k]["detail"]))

    def _parse(self, plac, parish=None):
        """{detail: [parts as written], parish, town, landskap, lan,
        country}, as written; `parish` (a parish already known for the
        place, e.g. the gazetteer's) fills a parish the string leaves out."""
        parts = gazetteer.plac_parts(plac)
        r = dict(detail=[], parish="", town="", landskap="", lan="", country="", _pi=None)
        c = gazetteer.abroad(parts)
        if c:                            # abroad: as written, no Swedish levels, no votes
            parts = [x.strip() for x in gazetteer.textfix.fix(plac or "").split(",") if x.strip()]
            words = parts[-1].replace("?", " ").split()
            if gazetteer.country_code(parts[-1]):
                r["country"] = parts.pop()
            elif not any(gazetteer.country_code(" ".join(words[i:])) for i in range(len(words))):
                r["country"] = gazetteer.COUNTRY_NAMES.get(c, ("",))[0]
            r["detail"] = parts
            r["abroad"] = True
            return r
        rest = []
        split = []
        for p in parts:                                  # "Dädesjö Kronobergs län": no comma
            m = TRAILING_LAN.match(p)
            split += [m[1], m[2]] if m and _lan_key(m[2]) in _LAN and _lan_key(p) not in _LAN else [p]
        for p in split:
            code = gazetteer.country_code(p)
            if code == "se":
                continue
            if code:
                r["country"] = r["country"] or p
            elif STIFT.search(p):
                continue                                     # "Linköpings stift": not a level shown
            elif lan_of(p):
                r["lan"] = r["lan"] or lan_of(p)
            elif _lan_key(p) in _LAN and not landskap_of(p) and not self._townish(p) \
                    and not self._candidates(p, []):
                r["lan"] = r["lan"] or _LAN[_lan_key(p)]          # "Goteborg Bohus", "Kronoberg"
            elif landskap_of(p) and not self._candidates(p, []):   # "Halland"; "Dalarna" may be either
                r["landskap"] = r["landskap"] or landskap_of(p)
            else:
                rest.append(p)
        regions = [x for x in (r["lan"], r["landskap"]) if x]
        given = parish and re.sub(r"\s+\([^()]*\)$", "", parish)

        def is_parish(i):
            p = rest[i]
            if CODE.search(p) or PARISH_KIND.search(p):
                return True
            if given and _key(parish_display(p)) == _key(given):
                return True
            if len(parts) == 1 or self.names.is_town(p):     # a lone name may be a farm; a town is none
                return False
            return bool(self._candidates(p, regions))
        pi = None
        for i in range(len(rest) - 1, -1, -1):
            if is_parish(i) and not (self._townish(rest[i]) and i and is_parish(i - 1)):
                pi = i
                break
        for i, p in enumerate(rest):
            if i == pi:
                r["parish"] = parish_display(p)
                r["_pi"] = len(r["detail"])
                m = CODE.search(p)
                if m and not r["lan"] and m["c"] in LAN_CODES:
                    r["lan"] = LAN_CODES[m["c"]]
            elif (pi is None or i > pi) and not r["town"] and self._townish(p):
                if pi is not None and not r["lan"] and _lan_key(p) in _LAN and not KOMMUN.search(p) \
                        and gazetteer.fold(parish_names.degenitive(p)) not in self._towns_of(rest[pi], regions):
                    r["lan"] = _LAN[_lan_key(p)]         # "Källeryd, Jönköping": the län, not the town
                else:
                    r["town"] = kommun_display(p)
            else:
                r["detail"].append(p)
        if not r["parish"] and given and _key(given) != _key(r["town"]) \
                and _key(given) not in {_key(d) for d in r["detail"]}:
            r["parish"] = given
        return r

    # -- completing it -------------------------------------------------------------

    def _vote(self, lv, value, want):
        c = self.votes.get((lv, _key(value)), {}).get(want)
        if not c:
            return None
        v, n = c.most_common(1)[0]
        return v if n * 3 >= 2 * sum(c.values()) else None

    def complete(self, plac, parish=None):
        r = self.parse(plac, parish)
        if r.get("abroad"):
            return r
        for _ in range(3):
            for want in ("town", "lan", "landskap"):
                if r[want] or (want == "town" and r["parish"] and self._townish(r["parish"])):
                    continue                             # Södertälje parish is its own town
                for lv in VOTES:
                    if want not in VOTES[lv] or not r[lv]:
                        continue
                    v = self._vote(lv, r[lv], want)
                    if v:
                        r[want] = v
                        break
            if not r["lan"] and r["parish"]:
                g = self._candidates(r["parish"], [r["landskap"]] if r["landskap"] else [])
                counties = {self.names.items[q]["county"] for v in g.values() for q in v} - {""}
                if len(g) == 1 and len(counties) == 1:
                    r["lan"] = counties.pop()
            if not r["landskap"] and r["lan"] in LAN_LANDSKAP:
                r["landskap"] = LAN_LANDSKAP[r["lan"]]
        return r

    def label(self, plac, parish=None):
        """The place as "detail, parish, town, landskap, län[, country]"."""
        r = self.complete(plac, parish)
        out = list(r["detail"])
        if r["parish"]:
            out.insert(len(out) if r["_pi"] is None else r["_pi"], r["parish"])
        for lv in ("town", "landskap", "lan", "country"):
            if r[lv] and _key(r[lv]) not in {_key(x) for x in out}:
                out.append(r[lv])
        return ", ".join(out)
