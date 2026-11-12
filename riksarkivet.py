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
it names; a mismatch means the citation and the volume disagree. The
record also links the volume's page in NAD, Riksarkivet's catalogue
("Post i NAD": sok.riksarkivet.se/arkiv/<id>, which redirects to
?postid=Arkis <GUID>), and its note often gives the page span ("1-250.",
"Uppslag 401-750."), read by `page_span`. The IIIF manifest's canvases
count the images (`image_count`, fetched gzipped).

The record of an archive (identifier SE/VALA/00100) is its whole
inventory: every series and volume with the same facts, in one request.
`volume` therefore reads a volume from its archive's inventory, and
`image_volume` and `resolve` (a code damaged in copying: spaces lost, l
for 1) search that list instead of asking volume by volume. Inventories
are cached beside the volume cache (`*_inventory.json`, not committed:
large, and rebuilt on demand). Wikidata's link for a reference code,
?postid=ArkisRef <code>, works for whole volume codes too, but only in a
browser (scripts get a captcha): a link for people, never a lookup.

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
import gzip
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


# A page span at the start of a volume's note: "1-300.", "I. 1 - 275. Södra
# delen.", "Uppslag 401-750.", "Volym 1. Uppslag 1-350.", "I. Fol. 1-200.".
SPAN = re.compile(r"^(?:(?:Volym|Bok)\s+\w+\.\s*)?(?:[IVX]+\.\s*)?"
                  r"(?:(Uppslag|Fol\.?|Folio|Sid(?:or|a)?\.?|s\.|Pag\.?)\s*)?"
                  r"(\d{1,4})\s*[-–]\s*(\d{1,4})(?![\d-])", re.I)


def page_span(note):
    """(first, last, unit) from the start of a volume's note, or None.
    unit is "uppslag" (numbered openings), "folio" or "page". Year spans
    (1918-1938) are not page spans."""
    m = SPAN.match((note or "").strip())
    if not m:
        return None
    a, b = int(m.group(2)), int(m.group(3))
    if b <= a or (a >= 1500 and b >= 1500 and b - a < 300):
        return None
    w = (m.group(1) or "").lower()
    unit = "uppslag" if w.startswith("uppslag") else "folio" if w.startswith("fol") else "page"
    return a, b, unit


def compact(code):
    """A reference code as copying damages it: no spaces, one case, and
    I, l and 1 (O and 0) alike."""
    return re.sub(r"\s+", "", code).lower().translate(str.maketrans("l1o", "ii0"))


def image_url(images, n):
    return f"https://sok.riksarkivet.se/bildvisning/{images}_{int(n):05d}"


def guess_image(page, pages, count):
    """The image a page is likely on, from its place in the volume's page
    span ("1-250") and image count: a guess (look a few images either side),
    0 when it can't be made."""
    m = re.match(r"(\d+)-(\d+)", pages or "")
    try:
        p, n = int(page), int(float(count))
    except (TypeError, ValueError):
        return 0
    if not m or not n:
        return 0
    a, b = int(m.group(1)), int(m.group(2))
    if not a <= p <= b:
        return 0
    return min(n, max(1, round(1 + (n - 1) * (p - a) / max(1, b - a))))


def link(r):
    """The best Riksarkivet link for a citation row (volume_refs.csv
    columns): (url, how) with how "image" (the cited image), "≈image" (a
    guess from the page), "volume" (the image viewer) or "catalogue" (NAD);
    ("", "") when there is none. Riksarkivet's images are free, so these
    stand in for MyHeritage's and Arkiv Digital's paywalled links."""
    g = lambda k: str(r.get(k, "") or "")
    if g("image_id") and g("image_no"):
        return image_url(g("image_id"), int(float(g("image_no")))), "image"
    if g("ra_status") != "found":
        return "", ""
    n = guess_image(g("page"), g("ra_pages"), g("ra_image_count"))
    if n and g("ra_images"):
        return image_url(g("ra_images"), n), "≈image"
    if g("ra_viewer"):
        return g("ra_viewer"), "volume"
    return (g("ra_nad"), "catalogue") if g("ra_nad") else ("", "")


def archive_of(code):
    return "/".join(code.split("/")[:3])


class Riksarkivet:
    def __init__(self, cache=None):
        self.cache_path = Path(cache) if cache else None
        self.cache, self.inv = {}, {}
        if self.cache_path and self.cache_path.exists():
            self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.inv_path = self.cache_path.with_name(self.cache_path.stem + "_inventory.json") \
            if self.cache_path else None
        if self.inv_path and self.inv_path.exists():
            self.inv = json.loads(self.inv_path.read_text(encoding="utf-8"))

    def save(self):
        if self.cache_path:
            self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=0),
                                       encoding="utf-8")
            self.inv_path.write_text(json.dumps(self.inv, ensure_ascii=False, separators=(",", ":")),
                                     encoding="utf-8")

    def volume(self, code, offline=False):
        """Reference code -> dict(code, years, note, images, viewer,
        manifest, nad, pages) or None when Riksarkivet has no such volume.
        Read from the archive's inventory; entries cached before NAD links
        were kept are refreshed from it."""
        hit = self.cache.get(code, False)
        if offline or hit is None or (hit and "nad" in hit):
            return hit or None
        inv = self.inventory(archive_of(code))
        if inv is not None and code in inv:
            self.cache[code] = inv[code]
            return inv[code]
        if hit:                                   # gone from the inventory: keep what we had
            return hit
        v = self._record(code)
        self.cache[code] = v
        return v

    def inventory(self, archive, offline=False):
        """Archive reference code -> {volume code: volume dict}, or None if
        Riksarkivet has no record of the archive."""
        if archive in self.inv or offline:
            return self.inv.get(archive)
        raw = self._get(archive)
        out = None
        if raw is not None:
            root = ET.fromstring(raw)
            out = {}
            for c in root.iter():
                if c.tag.endswith("}c") and "volym" in (c.get("level"), c.get("otherlevel")):
                    v = _parse_unit(c)
                    if v:
                        out[v["code"]] = v
        self.inv[archive] = out
        return out

    def resolve(self, code, offline=False):
        """A volume whose code differs from `code` only as copying damages
        one (compact), when exactly one in the archive's inventory does."""
        inv = self.inventory(archive_of(code), offline=offline) or {}
        hits = [v for c, v in inv.items() if compact(c) == compact(code)]
        return hits[0] if len(hits) == 1 else None

    def image_count(self, v, offline=False):
        """Number of images in the volume (canvases of its IIIF manifest),
        kept in the volume dict; None without a manifest."""
        if not v or not v.get("manifest"):
            return None
        if "image_count" in v or offline:
            return v.get("image_count")
        req = urllib.request.Request(v["manifest"], headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
        try:
            time.sleep(0.2)
            r = urllib.request.urlopen(req, timeout=60)
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            d = json.loads(raw)
            n = len(d["items"] if "items" in d else d["sequences"][0]["canvases"])
        except (OSError, ValueError, KeyError, IndexError):
            return None
        v["image_count"] = n
        if v["code"] in self.cache and self.cache[v["code"]] is not v:
            self.cache[v["code"]]["image_count"] = n
        return n

    def _record(self, code):
        raw = self._get(code)
        return _parse(code, raw) if raw is not None else None

    def _get(self, identifier):
        """The OAI-PMH record for a reference code, or None if it doesn't exist."""
        url = OAI + "?" + urllib.parse.urlencode(
            dict(verb="GetRecord", identifier=identifier, metadataPrefix="oai_ape_ead"))
        for attempt in range(4):
            time.sleep(0.5)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                raw = urllib.request.urlopen(req, timeout=60).read()
                break
            except urllib.error.HTTPError as e:     # 404 + idDoesNotExist
                raw = e.read()
                if b"idDoesNotExist" in raw:
                    return None
                if 400 <= e.code < 500 and e.code != 429:
                    return None     # a request Riksarkivet will never answer (bad code)
                time.sleep(5 * (attempt + 1))
            except OSError:
                time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError(f"Riksarkivet unreachable for {identifier}")
        return None if b"idDoesNotExist" in raw else raw


    def image_volume(self, image_id, archives, offline=False):
        """The volume whose image series is `image_id`, among the volumes of
        `archives` (reference codes), or None. Riksarkivet's records list
        each volume's image series, so a bare image link is matched exactly,
        not guessed; the candidate archives come from the event it is cited
        for; each archive's inventory lists every volume."""
        for v in self.cache.values():               # seen already
            if isinstance(v, dict) and v.get("images") == image_id:
                return v
        for archive in archives:
            for code, v in (self.inventory(archive, offline=offline) or {}).items():
                if v.get("images") == image_id:
                    self.cache[code] = v
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
    arch = next((e for e in root.iter() if e.tag.endswith("archdesc")), root)
    v = _parse_unit(arch, own=False)
    if v:
        v["code"] = code
    return v


def _parse_unit(el, own=True):
    """One volume's facts from its EAD element (an inventory's <c>, or a
    record's <archdesc>). With own, only the element's own <did> and
    notes are read, not those of units inside it."""
    def kids(e):
        return [d for k in e if not k.tag.endswith("}c") for d in k.iter()] if own else list(e.iter())
    did = next((k for k in el if k.tag.endswith("did")), None)
    if did is None:
        return None
    code = next((e.text for e in did if e.tag.endswith("unitid")), "") or ""
    date = next((e.text for e in did if e.tag.endswith("unitdate")), "") or ""
    notes = [" ".join("".join(p.itertext()).split())
             for e in kids(el) if e.tag.endswith(("odd", "scopecontent"))
             for p in e if p.tag.endswith("p")]
    note = " ".join(n for n in notes if n)
    out = dict(code=code.strip(), years=date.replace("--", "–"), note=note,
               images="", viewer="", manifest="", nad="", pages="")
    for e in did:
        if not e.tag.endswith("dao"):
            continue
        href, role = e.get(XLINK + "href", ""), e.get(XLINK + "role", "")
        if role == "MANIFEST":
            out["manifest"] = href
        m = re.search(r"bildvisning/(\w+)", href) or re.search(r"arkis!(\w+?)(?:_\d+)?/", href)
        if m and not out["images"]:
            out["images"] = m.group(1)
            out["viewer"] = f"https://sok.riksarkivet.se/bildvisning/{m.group(1)}"
    for e in kids(el):
        if e.tag.endswith("extref") and "Post i NAD" in "".join(e.itertext()):
            out["nad"] = e.get(XLINK + "href", "")
            break
    span = page_span(note)
    if span:
        out["pages"] = f"{span[0]}-{span[1]}" + ("" if span[2] == "page" else f" {span[2]}")
    return out


if __name__ == "__main__":
    ra = Riksarkivet()
    for c in sys.argv[1:]:
        if c.startswith("SE/"):
            print(json.dumps(ra.volume(c) or ra.resolve(c), ensure_ascii=False, indent=1))
        else:
            print(c, ra.archive_codes(c))
