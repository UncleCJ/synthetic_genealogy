"""
Riksarkivet volumes by reference code, through its open OAI-PMH service
(no key, no captcha):

    https://oai-pmh.riksarkivet.se/OAI/?verb=GetRecord
        &identifier=SE/VALA/00472/A II a/3&metadataPrefix=oai_ape_ead

A reference code is the parish archive (SE/VALA/00472, Wikidata P5324)
plus series and volume (A II a/3). One record gives:

- the volume's own year range ("1905--1910"),
- a content note, often the part of the parish or the page span
  ("I. 1 - 250. Södra delen.") - locality inside the book,
- the image series id (80007153): the volume in the image viewer is
  https://sok.riksarkivet.se/bildvisning/80007153, and a citation's
  "bildid: 80007153_00141" is image 141 of it; also a IIIF manifest.

So a citation's bildid prefix should equal the image series of the volume
it names; a mismatch means the citation and the volume disagree.

Answers are cached (gazetteer/cache/riksarkivet.json, public); a missing volume is
cached as None. Sketch: tested on a handful of Västergötland and
Östergötland codes. Series names are the usual kyrkoarkiv scheme, which
some archives deviate from.

A parish's archive code (SE/VALA/00472) is found by name through the
open search API (data.riksarkivet.se/api/records), whose PartOfArchive
facet names each archive ("Ödeshögs kyrkoarkiv").

    python riksarkivet.py "SE/VALA/00472/A II a/3"
    python riksarkivet.py Gnosjö
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

OAI = "https://oai-pmh.riksarkivet.se/OAI/"
API = "https://data.riksarkivet.se/api/records"
UA = "synthetic-genealogy/0.1 (riksarkivet.py; research sketch)"
XLINK = "{http://www.w3.org/1999/xlink}"

# Series in a Swedish church archive (kyrkoarkiv). Volumes are cited as
# series/volume: "A II a/3" is the third volume of series A II a, never
# "A II" + "a 3".
SERIES = {
    "A I": "husförhörslängd", "A II a": "församlingsbok", "A II": "församlingsbok",
    "A III": "", "A II b": "församlingsbok (bilaga)",
    "B": "flyttningslängd", "B I": "inflyttningslängd", "B II": "utflyttningslängd",
    "C": "födelse- och dopbok", "C I": "födelse- och dopbok",
    "D": "konfirmationsbok", "D I": "konfirmationsbok",
    "E": "lysnings- och vigselbok", "E I": "lysnings- och vigselbok",
    "F": "död- och begravningsbok", "F I": "död- och begravningsbok",
    "H": "bilagor", "K": "räkenskaper", "L": "längder", "N": "kyrkostämma",
}


def series_name(series):
    return SERIES.get(series, "")


def refcode(archive, series, vol):
    return f"{archive}/{series}/{vol}" if archive and series and vol else ""


class Riksarkivet:
    def __init__(self, cache=None):
        self.cache_path = Path(cache) if cache else None
        self.cache = {}
        if self.cache_path and self.cache_path.exists():
            self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))

    def save(self):
        if self.cache_path:
            self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=0),
                                       encoding="utf-8")

    def volume(self, code, offline=False):
        """Reference code -> dict(code, years, note, images, viewer, manifest)
        or None when Riksarkivet has no such volume."""
        if code in self.cache or offline:
            return self.cache.get(code)
        url = OAI + "?" + urllib.parse.urlencode(
            dict(verb="GetRecord", identifier=code, metadataPrefix="oai_ape_ead"))
        for attempt in range(4):
            time.sleep(0.5)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                raw = urllib.request.urlopen(req, timeout=60).read()
                break
            except urllib.error.HTTPError as e:     # 404 + idDoesNotExist
                raw = e.read()
                if b"idDoesNotExist" in raw:
                    break
                if 400 <= e.code < 500 and e.code != 429:
                    # a request Riksarkivet will never answer (bad code):
                    # remember it, don't retry
                    self.cache[code] = None
                    return None
                time.sleep(5 * (attempt + 1))
            except OSError:
                time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError(f"Riksarkivet unreachable for {code}")
        self.cache[code] = _parse(code, raw)
        return self.cache[code]


    def image_volume(self, image_id, archives, series, max_vol=60, offline=False):
        """The volume whose image series is `image_id`, looked for among the
        volumes of `archives` (reference codes) in `series` ("C", "A I"),
        or None. Riksarkivet's volume records list their image series, so a
        bare image link is matched exactly, not guessed; the candidates
        come from the event it is cited for. Volumes are numbered from 1; a
        series is read until two numbers in a row have no volume. Every
        answer is cached, so a second run needs no network."""
        for v in self.cache.values():               # seen already
            if isinstance(v, dict) and v.get("images") == image_id:
                return v
        for archive in archives:
            for s in series:
                missing = 0
                for n in range(1, max_vol + 1):
                    v = self.volume(refcode(archive, s, n), offline=offline)
                    if not v:
                        missing += 1
                        if missing >= 2:
                            break
                        continue
                    missing = 0
                    if v.get("images") == image_id:
                        return v
        return None

    def archive_codes(self, parish, offline=False):
        """Parish name -> reference codes of archives captioned "<parish>
        kyrkoarkiv" or "<parish>s kyrkoarkiv" (one, normally; several if
        parishes share a name). Uses the open search API's PartOfArchive
        facet, so no Wikidata is needed."""
        key = f"archive:{parish}"
        if key in self.cache or offline:
            return self.cache.get(key, [])
        want = {f"{parish} kyrkoarkiv".lower(), f"{parish}s kyrkoarkiv".lower()}
        hits = self._api(text=parish, max=1)
        captions = [v["value"] for f in hits.get("facets", []) if f["name"] == "PartOfArchive"
                    for v in f["values"] if v["value"].lower() in want]
        codes = set()
        for cap in captions:
            r = self._api(text=parish, max=10, facet=f"PartOfArchive:{cap}")
            for item in r.get("items") or []:
                rc = item.get("metadata", {}).get("referenceCode", "")
                if rc.count("/") >= 2:
                    codes.add("/".join(rc.split("/")[:3]))
        self.cache[key] = sorted(codes)
        return self.cache[key]

    def _api(self, **params):
        url = API + "?" + urllib.parse.urlencode(params)
        for attempt in range(4):
            time.sleep(0.5)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                return json.load(urllib.request.urlopen(req, timeout=60))
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 500 and e.code != 429:
                    return {}
                time.sleep(5 * (attempt + 1))
            except OSError:
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"Riksarkivet search unreachable: {params}")


def _parse(code, raw):
    root = ET.fromstring(raw)
    if any(e.tag.endswith("error") for e in root.iter()):
        return None
    date = next((e.text for e in root.iter() if e.tag.endswith("unitdate")), "") or ""
    notes = [" ".join("".join(p.itertext()).split())
             for e in root.iter() if e.tag.endswith(("odd", "scopecontent"))
             for p in e if p.tag.endswith("p")]
    out = dict(code=code, years=date.replace("--", "–"), note=" ".join(n for n in notes if n),
               images="", viewer="", manifest="")
    for e in root.iter():
        if not e.tag.endswith("dao"):
            continue
        href, role = e.get(XLINK + "href", ""), e.get(XLINK + "role", "")
        if role == "MANIFEST":
            out["manifest"] = href
        m = re.search(r"bildvisning/(\w+)", href) or re.search(r"arkis!(\w+?)(?:_\d+)?/", href)
        if m and not out["images"]:
            out["images"] = m.group(1)
            out["viewer"] = f"https://sok.riksarkivet.se/bildvisning/{m.group(1)}"
    return out


if __name__ == "__main__":
    ra = Riksarkivet()
    for c in sys.argv[1:]:
        if c.startswith("SE/"):
            print(json.dumps(ra.volume(c), ensure_ascii=False, indent=1))
        else:
            print(c, ra.archive_codes(c))
