"""
Archive references in free text, read into one shape by named readers.

A reference points at a record volume (and a page or image in it), however
it was written down. Readers: riksarkivet (its own citation, with or
without the archive's name), arkivdigital, myheritage (household-
examination labels, line breaks squashed) and image (a bildvisning link or
"bildid:" alone). Examples of each form: docs/records.md, "References and
volumes".

`find(text)` returns every reference in a text, in order, each a dict with
`format` and the fields it could read (parish, town, archive, archive_code,
series, vol, vol_suffix, years, page, row, farm, image_id, image_no, aid,
county). Series are written as Riksarkivet writes them ("AIIa" -> "A II a").
A span is never read twice: a Riksarkivet citation wins over an Arkiv
Digital reading, and an image link right after a volume reference without
one is joined to it.

Sketch status (unvalidated beyond two family trees): Arkiv Digital's "Bild"
is its own image number, kept as `ad_image`, never `image_no`.
"""
import html
import re

# -- Riksarkivet ------------------------------------------------------------

RA_CITATION = re.compile(
    r"(?P<archive>[^,\n<>]+?),\s*(?P<series>[^,\n<>]+?),\s*"
    r"(?P<code>SE/[A-Z]+/\d+)(?:/(?P<sub>[^/()\n]+)/(?P<vol>[^\s()/]+))?"
    r"\s*\((?P<years>[^)]*)\)"
    r"(?:,\s*bildid:\s*(?P<bildid>\w+))?(?:,\s*sida\s*(?P<page>\d+))?")

# Led by the code, with a series and volume (a bare "SE/VALA/01234" is an
# archive, not a volume). A short name and a colon before it is the farm.
RA_CODE_LED = re.compile(
    r"(?:(?P<farm>[A-ZÅÄÖ][^\n:,;<>()]{0,40}?):\s*)?"
    r"(?P<code>SE/[A-Z]+/\d+)/(?P<sub>[^/()\n]+?)/(?P<vol>[^\s()/,]+)"
    r"\s*\((?P<years>[^)]*)\)"
    r"(?:,?\s*bildid:\s*(?P<bildid>\w+))?(?:,?\s*sida\s*(?P<page>\d+))?")

# -- Arkiv Digital ----------------------------------------------------------

_WORD = r"(?:S:t|S:ta|St\.|[A-ZÅÄÖÉ][\w\-']*)"
AD_REF = re.compile(
    rf"(?<![\w:])(?P<parish>{_WORD}(?:\s+(?:och\s+)?{_WORD}){{0,4}}?)"
    r"(?:\s*\((?P<county>[A-ZÅÄÖ]{1,2})\))?"
    r"\s+(?P<series>[A-HJ-Z](?:IV|I{1,3})?[a-z]{0,2})\s*:\s*(?P<vol>\d+)(?P<vol_letter>[a-z]?)"
    r"\s*\((?P<y1>\d{4})(?:\s*-\s*(?P<y2>\d{4}))?\)"
    r"(?:,?\s*[Bb]ild\s*(?P<img>\d+))?(?:\s*/\s*sid\s*(?P<page>\d+))?"
    r"(?:\s*\(AID:\s*(?P<aid>v\w+?)(?:\.b(?P<aid_img>\d+))?(?:\.s(?P<aid_page>\d+))?"
    r"\s*,\s*NAD:\s*(?P<code>SE/[A-Z]+/\d+)\s*\))?")

# -- MyHeritage --------------------------------------------------------------

# Variants seen (after squash):
#   "Bok: LandSwedenBokAnderstorp AIIa2, 1911 - 1921 ProvinsSmåland..."
#   "Bok: Land:SwedenBok:Källeryd_AIIa3-296, 1921 - 1941 Provins:..."
#   "BokStora Åby AI 20, 1891 - 1895", "BokHabo_AIIa5a-571, 1930 - 1941"
#   "Bok: Land Sweden, Bok Anderstorp AI14, 1891 - 1899" (tidied by hand)
#   "Bok: <tab>LandSwedenBokSigtuna, Sankt Olof och Sankt Per AI16, 1876 - 1880"
#   "Bok: LandSwedenBokRisinge,_Finspångs_kyrkobokföringsdistrikt_AIIa4-2229, ..."
#   "Bok: LandSwedenBokNorrköpings_S:t_Olai_AIIaa84-1397, 1935 - 1940..."
#   "Bok: LandSwedenBokAdolf Fredrik AI86, 1869Provins..." (one year)
#     One "X, " level before the name is kept as `town`: a town before its
#     congregation (Sigtuna), or the parish a kyrkobokföringsdistrikt belongs
#     to (Risinge); the volume stays under the second name, whose series it is.
_NAME = r"(?:S:ta|S:t|[^\n,:;])+?"
MH_BOK = re.compile(
    r"Bok:?\s*(?:[\w:]*?\s*Sweden,?\s*Bok:?\s*|Land:?\s*\w+?,?\s*Bok:?\s*)?"
    rf"(?:(?P<town>{_NAME}),\s*)?(?P<parish>{_NAME})[\s_]+"
    r"(?P<series>A\s?I{1,2}\s?[a-z]{0,2})\s?(?P<vol>\d+\s?[a-z]?)(?:-(?P<suffix>\d+))?"
    r"\s*,\s*(?P<y1>\d{4})(?:\s*-\s*(?P<y2>\d{4}))?")
MH_FIELD = {
    "farm": re.compile(r"Plats:?\s*(.+?)\s*Län"),
    "page": re.compile(r"Sida:?\s*(\d+)"),
    "row": re.compile(r"Rad:?\s*(\d+)"),
}

# -- images ------------------------------------------------------------------

BILD = re.compile(r"bildvisning/(?P<img>[A-Za-z]?\d+)_(?P<no>\d+)")
BILDID = re.compile(r"bildid:\s*(?P<img>[A-Za-z]?\d+)_(?P<no>\d+)")


# -- helpers -----------------------------------------------------------------

def series(s):
    """'AIIa' / 'A II a' -> 'A II a'; 'EI' -> 'E I'; 'AIIaa' -> 'A II aa'."""
    return " ".join(re.findall(r"IV|I{1,3}|[A-HJ-Z]|[a-z]+", (s or "").replace(" ", "")))


ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}


def order_key(years, archive, series_code, vol):
    """References in one order everywhere (roadmap, views): span (first,
    then last year; none last), archive name, then the series in the
    archive schema's order (records.md) and the volume, numerically."""
    ys = [int(y) for y in re.findall(r"\d{4}", years or "")]
    y0 = ys[0] if ys else 9999
    toks = (series_code or "").split()
    sk = tuple((1, ROMAN[t], "") if t in ROMAN and i else (0, 0, t) if t.isupper() else (2, 0, t)
               for i, t in enumerate(toks))
    vk = tuple(int(t) if t.isdigit() else t for t in re.findall(r"\d+|\D+", vol or ""))
    return (y0, ys[-1] if ys else y0, (archive or "").lower(), sk, tuple((isinstance(t, str), t) for t in vk))


def squash(s):
    """Collapse the line breaks and tabs MyHeritage puts inside a label."""
    return re.sub(r"\n\s*", "", s or "")


def clean(text):
    """HTML entities (also double-escaped ones) decoded, tags and the line
    separators MyHeritage keeps (U+2028) turned into line breaks."""
    t = text or ""
    for _ in range(3):
        u = html.unescape(t)
        if u == t:
            break
        t = u
    t = re.sub(r"<[^>]+>", "\n", t)
    return t.replace(" ", "\n").replace(" ", "\n")


def _years(a, b):
    return f"{a}-{b}" if b else (a or "")


def _ref(fmt, m, **fields):
    d = dict(format=fmt, text=m.group(0).strip(), start=m.start(), end=m.end())
    d.update({k: (v.strip() if isinstance(v, str) else v) for k, v in fields.items() if v})
    return d


# -- readers -----------------------------------------------------------------

def riksarkivet(text):
    out = []
    for m in RA_CITATION.finditer(text):
        img = BILDID.search(m.group(0))
        out.append(_ref("riksarkivet", m, archive=m["archive"], series_name=m["series"],
                        archive_code=m["code"], series=series(m["sub"] or ""),
                        vol=(m["vol"] or "").replace(" ", ""), years=m["years"] or "",
                        page=m["page"], image_id=img and img["img"],
                        image_no=img and str(int(img["no"]))))
    taken = [(r["start"], r["end"]) for r in out]
    for m in RA_CODE_LED.finditer(text):
        if any(a <= m.start("code") < b for a, b in taken):
            continue
        img = BILDID.search(m.group(0))
        out.append(_ref("riksarkivet", m, farm=m["farm"], archive_code=m["code"],
                        series=series(m["sub"]), vol=m["vol"].replace(" ", ""),
                        years=m["years"] or "", page=m["page"],
                        image_id=img and img["img"], image_no=img and str(int(img["no"]))))
    return out


def arkivdigital(text):
    out = []
    for m in AD_REF.finditer(text):
        out.append(_ref("arkivdigital", m, parish=m["parish"], county=m["county"],
                        series=series(m["series"]), vol=m["vol"] + (m["vol_letter"] or ""),
                        years=_years(m["y1"], m["y2"]), page=m["page"] or m["aid_page"],
                        ad_image=m["img"] or m["aid_img"], aid=m["aid"], archive_code=m["code"]))
    return out


def myheritage(text):
    """MyHeritage labels in `text` (squashed first; spans refer to the
    squashed text). Page, row and farm come from the fields after the label."""
    sq = squash(text)
    out = []
    for m in MH_BOK.finditer(sq):
        tail = sq[m.end():m.end() + 300]
        extra = {k: (rx.search(tail) or [None, None])[1] for k, rx in MH_FIELD.items()}
        out.append(_ref("myheritage", m, parish=m["parish"].replace("_", " "),
                        town=(m["town"] or "").replace("_", " "), mh_series=m["series"],
                        series=series(m["series"]), vol=m["vol"].replace(" ", ""),
                        vol_suffix=m["suffix"], years=_years(m["y1"], m["y2"]),
                        label=sq[m.start():m.end() + 160].split("Se hushåll")[0].strip(),
                        **extra))
    return out


def images(text):
    out = []
    for rx in (BILDID, BILD):
        for m in rx.finditer(text):
            out.append(_ref("image", m, image_id=m["img"], image_no=str(int(m["no"]))))
    out.sort(key=lambda r: r["start"])
    seen, keep = set(), []
    for r in out:                     # a link and its "bildid:" name one image
        if r["image_id"] + r["image_no"] not in seen:
            seen.add(r["image_id"] + r["image_no"])
            keep.append(r)
    return keep


def find(text, mh=True):
    """Every reference in `text`, in order (see the module docstring).
    Volume references (riksarkivet, arkivdigital) are read on the cleaned
    text; MyHeritage labels on the squashed raw text, appended after them."""
    t = clean(text)
    vols = riksarkivet(t)
    taken = [(r["start"], r["end"]) for r in vols]
    for r in arkivdigital(t):
        if not any(a < r["end"] and r["start"] < b for a, b in taken):
            vols.append(r)
    vols.sort(key=lambda r: r["start"])
    for img in images(t):
        inside = next((v for v in vols if v["start"] <= img["start"] < v["end"]), None)
        if inside:
            continue
        before = next((v for v in reversed(vols)
                       if v["end"] <= img["start"] and img["start"] - v["end"] < 60), None)
        if before and not before.get("image_id"):
            before.update(image_id=img["image_id"], image_no=img["image_no"])
        elif not before or before.get("image_id") != img["image_id"]:
            vols.append(img)
    vols.sort(key=lambda r: r["start"])
    return vols + (myheritage(text) if mh else [])


def volume(ref):
    """'Parish A II a/2 (1906-1921)' for display, as far as the reference
    names it."""
    head = ref.get("parish") or ref.get("archive_code") or "?"
    sv = f"{ref.get('series', '')}/{ref.get('vol', '')}".strip("/")
    return f"{head} {sv}".strip() + (f" ({ref['years']})" if ref.get("years") else "")
