"""
The research as it sits in the record volumes: which parish books, pages
and farms the tree's citations point at, and who on those pages is family.

Every citation is reduced to one shape, with a tier: ra-full (Riksarkivet
citation, or an Arkiv Digital reference with its volume), ra-link (only a
bildvisning URL), mh-record (MyHeritage household-examination record),
mh-index (other MyHeritage collections), tree (other trees and sites),
plac-only (a place and no citation). `ref_format` says which reader read a
row. Volumes are keyed (parish, series, volume); each cited person is
classed against the proband (ancestor, relative with FF/FM/MF/MM branch,
spouse of a relative, unlinked). Parishes resolve to Wikidata items
(places.py), by archive code first. The references themselves are read by
references.py, also in notes, addresses and event values (`ref_in`).
How it works: docs/records.md, "References and volumes". The Archives
page is written by archivesview.py, the farm and home reports are in
homes.py, and kinship is lineage.kinship.

Parishes cited only as places can be named in family.toml:
`[volumes] parishes = ["..."]`. Sketch status (unvalidated): written
against one Gramps export of a MyHeritage tree; MyHeritage page and row
numbers are its indexers' reading, Riksarkivet "sida" the book's own page.
Not handled: Sveriges dödbok, the volume suffix in "Källeryd_AIIa3-296"
(kept as written), farm names' spelling variants.

    python volumes.py                 # volume_refs.csv + archives.html in data/output/
    python volumes.py --wikidata      # also resolve parishes by name on Wikidata (slow)
    python volumes.py --no-riksarkivet  # skip volume lookups (riksarkivet.py)
    python volumes.py farm Hagelstorp # one farm across volumes, as text
    python volumes.py home            # where to find ancestors in their parents' household at birth
"""
import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from sg.views import archivesview
from sg.readers import gedcom_io
from sg.records import homes
from sg.common import identity
from sg.common import lineage
from sg.records import places
from sg.readers import references
from sg.records import riksarkivet

MH_ITEM = re.compile(r"collection-(?P<coll>\d+)/[^?]*\?(?:[^ ]*&)?itemId=(?P<item>\d+)")
# The reference readers live in references.py; these names stay for callers.
BILD, BILDID, MH_BOK, MH_FIELD = references.BILD, references.BILDID, references.MH_BOK, references.MH_FIELD
HEMVIST = re.compile(r"(?:Hemvist:\s*Mellan|Residence:\s*Between)\s*(\d{4})\s*(?:och|and)\s*(\d{4})"
                     r"\s*-\s*([^\n]+)")     # Swedish or English site
# The record's own birth column, as MyHeritage indexed it: "Födelse: 5 okt 1929 - Habo skb."
FODELSE = re.compile(r"(?:Födelse|Birth):\s*([^&<\n]+)")

TREE_SOURCE = re.compile(r"Web Site|släktplats|Nettsiden|släktträd|släkträd|Family Tree"
                         r"|WikiTree|Geni|Ratsit|Tributes|Berömda|Biografiska", re.I)
# Keeps the genitive ("Källeryds"); normalise() joins it to "Källeryd".
ARCHIVE_SOURCE = re.compile(r"^(?P<name>.+?)\s+kyrkoarkiv", re.I)

EVENTS = {"BIRT": "birth", "CHR": "baptism", "DEAT": "death", "BURI": "burial",
          "MARR": "marriage", "RESI": "residence", "EMIG": "emigration",
          "IMMI": "immigration", "OCCU": "occupation", "EVEN": "event", "CENS": "census"}


# What a parish name looks like; MyHeritage's raw 2026 export cuts and
# overwrites its labels ("Bok: andPlatsLundkvistr", "ndSwedenBokÖreryd"),
# so fragments must not become parishes.
_PARISH_OK = re.compile(r"^[A-ZÅÄÖÉ][\w\-'. åäöÅÄÖé()]*$")
_PARISH_BAD = re.compile(r"Bok|Sweden|Plats|Sida|Län\b|Källa|Provins|Församling|Rad\b|Hemvist"
                         r"|Book|Location|Page\b|County|Province|Line\b|Residence")


def valid_parish(name):
    name = re.sub(r"^Källa:\s*", "", (name or "").strip())
    return name if _PARISH_OK.match(name) and not _PARISH_BAD.search(name) else ""


_squash = references.squash
_series = references.series


def _vol(v):
    return v.replace(" ", "")


def _first(node, tag):
    return next((s for s in node["sub"] if s["tag"] == tag), None)


def _val(node, *path):
    """Value at a tag path, NFC-normalised (MyHeritage text mixes in
    decomposed å/ä/ö, which would split one parish into two)."""
    for t in path:
        node = _first(node, t) if node else None
    return unicodedata.normalize("NFC", node["value"]) if node else ""


# -- extraction ----------------------------------------------------------------

def _citation(sour, titles):
    """One SOUR citation node -> dict of what it says about a volume. The
    references in it are read by references.find; this decides the tier."""
    sid = sour["value"]
    title = titles.get(sid, "")
    page_field = _val(sour, "PAGE")
    text = _val(sour, "DATA", "TEXT")
    c = _blank_citation(sid, title, page_field)
    item = MH_ITEM.search(page_field) or MH_ITEM.search(text)
    if item:
        c["mh_collection"], c["mh_item"] = item["coll"], item["item"]
    mh = _myheritage_label(text)
    if not mh and re.search("Boo?k", text):     # a label the pattern did not read: kept for tracing
        c["mh_label"] = _unread_label(text)
    ref = _volume_ref(text, page_field)
    bild = _image_ref(page_field, text)
    if bild:
        c["image_id"], c["image_no"] = bild["img"], str(int(bild["no"]))
    if ref:
        _cite_volume(c, ref, mh, text, title)
    elif bild:
        _cite_image(c, mh, title)
    elif mh:
        _cite_myheritage(c, mh, title)
    else:
        _cite_other(c, text, title, item)
    return c


def _blank_citation(sid, title, page_field):
    """The citation row with every field empty but the source and its URL."""
    url = re.search(r"https?://\S+", page_field)
    return dict(source=sid, source_title=title, url=url.group(0) if url else "", tier="other",
                parish="", archive_code="", series="", vol="", vol_suffix="",
                years="", page="", row="", farm="", image_id="", image_no="",
                mh_collection="", mh_item="", resourced="", ref_format="", ref_in="citation")


def _myheritage_label(text):
    """What a MyHeritage record label in the text says ("Bok: ..."), or {}."""
    bok = next(iter(references.myheritage(text)), None)
    if not bok:
        return {}
    mh = dict(mh_label=bok["label"], parish=bok.get("parish", ""),
              town=valid_parish(bok.get("town", "")), series=bok.get("series", ""),
              vol=bok.get("vol", ""), vol_suffix=bok.get("vol_suffix", ""),
              years=bok.get("years", ""))
    mh.update({k: bok[k] for k in ("farm", "page", "row") if bok.get(k)})
    fd = FODELSE.search(unicodedata.normalize("NFC", text))
    if fd:
        mh["born"] = fd[1].strip()
    if not mh.get("farm"):
        farm = _residence_farm(text, mh)
        if farm is not None:
            mh["farm"] = farm
    return mh


def _residence_farm(text, mh):
    """The farm on the residence line, for a damaged "Plats" field; None
    when the line gives none."""
    # only when that line names this record's parish after it
    # ("Gården, Sigtuna, Sankt Olof och Sankt Per, ..."), so a line
    # that starts with a parish or town gives no farm
    hv = HEMVIST.search(text)
    if not hv:
        return None
    parts = [x.strip() for x in hv[3].split(",")]
    names = {_key(mh["parish"]), _key(mh["town"])} - {""}
    after = {_key(x) for x in parts[1:3]}
    if len(parts) > 1 and _key(parts[0]) not in names and names & after:
        return parts[0]
    return None


def _unread_label(text):
    """The text from "Bok" ("Book") on, of a label the pattern did not read."""
    sq = _squash(text)
    return references.HOUSEHOLD.split(sq[re.search("Boo?k", sq).start():][:200])[0].strip()


def _volume_ref(text, page_field):
    """The first volume reference (not a bare image) in the citation text,
    else in the PAGE; None if neither has one."""
    # searched apart: joined, the URL would run into the archive name
    ref = None
    for part in (text, page_field):
        ref = ref or next((r for r in references.find(part, mh=False)
                           if r["format"] != "image"), None)
    return ref


def _image_ref(page_field, text):
    """A Riksarkivet image (bildvisning) match in PAGE and text, or None."""
    flat = re.sub(r"<[^>]+>", " ", page_field + "\n" + text)
    return BILDID.search(flat) or BILD.search(flat)


def _cite_volume(c, ref, mh, text, title):
    """Tier ra-full: a volume reference, Riksarkivet's or Arkiv Digital's."""
    c.update(tier="ra-full", ref_format=ref["format"], archive_code=ref.get("archive_code", ""),
             years=ref.get("years", ""), page=ref.get("page", ""),
             series=ref.get("series", ""), vol=ref.get("vol", ""))
    if ref["format"] == "riksarkivet":
        # only a church archive names a parish (not a police or orphanage archive)
        m = _church_archive(ref, text, title)
        c["parish"] = valid_parish(m["name"].strip()) if m else ""
        c["ra_archive"] = ref.get("archive", "")
    else:                                     # Arkiv Digital: the parish as such
        c["parish"] = valid_parish(ref.get("parish", ""))
        c["aid"] = ref.get("aid", "")
    if mh:
        _keep_indexer_reading(c, mh)


def _church_archive(ref, text, title):
    """The "X kyrkoarkiv" match naming the archive, or None."""
    # "X kyrkoarkiv, Series, Subseries, SE/..." has one field more than
    # the pattern expects: look for the archive name anywhere before it
    return ARCHIVE_SOURCE.match(ref.get("archive", "")) \
        or re.search(r"(?P<name>[^,>\n]+?)\s+kyrkoarkiv", text) \
        or ARCHIVE_SOURCE.match(title)


def _keep_indexer_reading(c, mh):
    """A MyHeritage record later tidied with the archive citation: keep the
    indexer's reading beside it and flag disagreement."""
    c["farm"], c["row"], c["born"] = mh.get("farm", ""), mh.get("row", ""), mh.get("born", "")
    c["mh_label"] = mh["mh_label"]
    page = mh.get("page", "?")
    c["mh_volume"] = f"{mh['parish']} {mh['series']} {mh['vol']} ({mh['years']}) p. {page}"
    other_volume = (mh["series"], mh["vol"]) != (c["series"], c["vol"])
    other_page = mh.get("page") and c["page"] and mh["page"] != c["page"]
    if other_volume or other_page:
        c["conflict"] = "MyHeritage label and archive citation differ"


def _cite_image(c, mh, title):
    """Tier ra-link: an image link only; the volume from the MyHeritage label."""
    c["tier"], c["ref_format"] = "ra-link", "image"
    m = ARCHIVE_SOURCE.match(title)
    c["parish"] = valid_parish(m["name"] if m else mh.get("parish", ""))
    c["ra_archive"] = title if m else ""
    for k in ("series", "vol", "years", "page", "row", "farm"):
        c[k] = c[k] or mh.get(k, "")


def _cite_myheritage(c, mh, title):
    """Tier mh-record: a MyHeritage household-examination record."""
    mh["parish"] = valid_parish(mh.get("parish"))
    c.update(mh, tier="mh-record", ref_format="myheritage")
    if ARCHIVE_SOURCE.match(title):
        c["resourced"] = title


def _cite_other(c, text, title, item):
    """No volume: a residence line's farm and years, and the tier from the
    source title and URL (tree, mh-index, ra-link or other)."""
    hv = HEMVIST.search(text)
    if hv and not c["farm"]:
        c["farm"] = hv[3].split(",")[0].strip()
        c["years"] = f"{hv[1]}-{hv[2]}"
    if TREE_SOURCE.search(title) or "collection-4000" in c["url"] or "/person-" in c["url"]:
        c["tier"] = "tree"
    elif item or "myheritage" in c["url"]:
        c["tier"] = "mh-index"
    elif ARCHIVE_SOURCE.match(title):
        c["tier"] = "ra-link" if c["url"] else "other"
        c["parish"] = valid_parish(ARCHIVE_SOURCE.match(title)["name"])


def _addr(event):
    """MyHeritage 2026 writes residences as ADDR (ADR1 farm, ADR2 croft,
    CITY parish, STAE county, CTRY country) instead of PLAC. A line holding
    a volume reference ("1823-1827. Byn AI:7 (1821-1831) Bild 261 / sid 509
    (AID: ..., NAD: ...)") is a citation, not a place: `_noted` reads it."""
    a = _first(event, "ADDR")
    if not a:
        return ""
    parts = [a["value"]] + [_val(a, t) for t in ("ADR1", "ADR2", "ADR3", "CITY", "STAE", "CTRY")]
    parts = [x for x in parts if x and not any(r["format"] != "image"
                                               for r in references.find(x, mh=False))]
    return ", ".join(x.strip() for x in parts if x and x.strip())


# Where a reference may be written outside a source citation: a note, an
# address line, a place, or an event's own value ("1 EVEN Byn (F) AI:1 ...").
NOTED_IN = ("NOTE", "ADDR", "PLAC")


def _noted(text, where):
    """Rows for the volume and image references written in `text`, a note
    or an address rather than a source citation: tier ra-full for a volume,
    ra-link for an image alone; `ref_in` says where ("note:NOTE")."""
    out = []
    for r in references.find(text, mh=False):
        c = dict(source="", source_title="", url="", ref_format=r["format"], ref_in=f"note:{where}",
                 tier="ra-link" if r["format"] == "image" else "ra-full",
                 parish=valid_parish(r.get("parish", "")), archive_code=r.get("archive_code", ""),
                 series=r.get("series", ""), vol=r.get("vol", ""), vol_suffix="",
                 years=r.get("years", ""), page=r.get("page", ""), row="",
                 farm=r.get("farm", ""), image_id=r.get("image_id", ""),
                 image_no=r.get("image_no", ""), aid=r.get("aid", ""), ref_text=r["text"][:200])
        m = ARCHIVE_SOURCE.match(r.get("archive", ""))
        if m:
            c["parish"], c["ra_archive"] = valid_parish(m["name"].strip()), r["archive"]
        out.append(c)
    return out


def _ref_key(r):
    """What a reference points at, for dropping a noted one that a source
    citation of the same person already gives."""
    if r.get("vol"):
        return (r.get("archive_code") or _key(r.get("parish")), r.get("series"), r.get("vol"),
                r.get("page"))
    return ("image", r.get("image_id"), r.get("image_no")) if r.get("image_id") else None


def extract(records):
    """Citations and uncited places for every person, as flat rows.
    Family-level citations (marriages) are given to both spouses. Volume
    references written in notes, addresses and event values become rows
    too (`ref_in` "note:<tag>"), unless a source citation of the same
    person already points at that volume and page."""
    titles = {r["xref"]: _val(r, "TITL") for r in records if r["tag"] == "SOUR"}
    notes = {r["xref"]: r["value"] for r in records if r["tag"] == "NOTE" and r["xref"]}
    rows = []

    def add_noted(text, where, owners, event, place, date):
        for c in _noted(text, where):
            for o in owners:
                rows.append(dict(c, person=o, event=event, event_place=place, event_date=date))

    def walk(node, owners, event, place, date):
        for s in node["sub"]:
            if s["tag"] == "SOUR" and s["value"].startswith("@"):
                c = _citation(s, titles)
                d = _val(s, "DATA", "DATE")
                for o in owners:
                    rows.append(dict(c, person=o, event=event, event_place=place,
                                     event_date=date, cite_date=d))
            elif s["tag"] in EVENTS:
                ev = EVENTS[s["tag"]]
                if s["tag"] == "EVEN":
                    ev = _val(s, "TYPE") or ev
                pl, dt = _val(s, "PLAC") or _addr(s), _val(s, "DATE")
                n_before = len(rows)
                if s["value"] not in ("", "Y"):
                    add_noted(s["value"], s["tag"], owners, ev, pl, dt)
                walk(s, owners, ev, pl, dt)
                if pl and len(rows) == n_before:      # an event with no citation
                    for o in owners:
                        rows.append(dict(tier="plac-only", person=o, event=ev,
                                         event_place=pl, event_date=dt))
            elif s["tag"] in NOTED_IN:
                texts = [notes.get(s["value"], s["value"])]
                if s["tag"] == "ADDR":
                    texts += [_val(s, t) for t in ("ADR1", "ADR2", "ADR3")]
                for t in texts:
                    add_noted(t, s["tag"], owners, event, place, date)
    for r in records:
        if r["tag"] == "INDI":
            walk(r, [r["xref"]], "person", "", "")
        elif r["tag"] == "FAM":
            owners = [v for v in (_val(r, "HUSB"), _val(r, "WIFE")) if v]
            walk(r, owners, "family", "", "")
    cited = {(r["person"], _ref_key(r)) for r in rows
             if r.get("ref_in") == "citation" and _ref_key(r)}
    seen, out = set(), []
    for r in rows:
        if str(r.get("ref_in", "")).startswith("note:"):
            k = (r["person"], _ref_key(r))
            if k in cited or (k, r["event"]) in seen:
                continue
            seen.add((k, r["event"]))
        out.append(r)
    return out


# -- normalising parishes and volumes -------------------------------------------

def _key(name):
    return re.sub(r"[\s_-]+", " ", (name or "").strip().lower())


# What follows a parish's name in a PLAC part ("Källeryds socken"). Narrower
# than gazetteer.PARISH_SUFFIX: no "kyrkoförsamling", "lands förs.", or a
# trailing full stop after the word.
PLAC_SUFFIX = re.compile(r"\s+(?:lands- och stadsförsamling|(?:stads|lands|domkyrko|kyrko)?"
                         r"(?:församling|förs\.?)|socken|kyrka|lf\.?|sf\.?)$", re.I)


# A part that says it is a parish, known or not ("Västerlanda förs.").
EXPLICIT_PARISH = re.compile(r"\s+(?:lands- och stadsförsamling|(?:stads|lands|domkyrko|kyrko)?"
                             r"(?:församling|förs\.?)|socken)$", re.I)


def degenitive(name):
    """Archive names are genitive: "Källeryds kyrkoarkiv", but "Gränna
    kyrkoarkiv", "Linderås kyrkoarkiv". Drop a final s after a consonant
    (heuristic: a parish whose own name ends in consonant + s would lose it)."""
    return re.sub(r"(?<=[b-df-hj-np-tv-zß])s$", "", name.strip())


def normalise(rows, extra_parishes=(), reference=None):
    """Join parish spellings, resolve ra-link volumes through image ids,
    derive farm and parish from PLAC for uncited events. Parish names come
    from the record citations; `extra_parishes` adds parishes that appear
    only in places (no volume cited yet), so PLAC parsing finds them. Other
    parishes come from the full list (parish_names.py; `reference` replaces
    it, for tests)."""
    _degenitive_archive_parishes(rows)
    known = _known_parishes(rows, extra_parishes)
    _join_spellings(rows, known)
    code_of, parish_of = _codes_and_parishes(rows)
    _parishes_from_codes(rows, parish_of)
    _volumes_from_images(rows)
    _codes_from_parishes(rows, code_of)
    _places_from_plac(rows, known, reference)
    return rows


def _degenitive_archive_parishes(rows):
    """"Källeryds kyrkoarkiv" -> Källeryd, for parishes read from archive names."""
    for r in rows:
        archive_tier = r.get("tier") in ("ra-full", "ra-link", "other")
        if archive_tier and r.get("parish") \
                and r.get("ref_format") != "arkivdigital":  # Arkiv Digital: not genitive
            r["parish"] = degenitive(r["parish"])


def _known_parishes(rows, extra_parishes):
    """key -> spelling of every parish the family's citations name: MyHeritage's
    first, then `extra_parishes`, then the archive citations'."""
    mh_names = {_key(r["parish"]): r["parish"] for r in rows
                if r.get("tier") == "mh-record" and r["parish"]}
    # in row order, not hash order: which name wins a parish group follows it
    archive_names = dict.fromkeys(_key(r["parish"]) for r in rows
                                  if r.get("tier") in ("ra-full", "ra-link") and r.get("parish"))
    known = dict(mh_names)
    for p in extra_parishes:
        known.setdefault(_key(p), unicodedata.normalize("NFC", p))
    for k in archive_names:
        if k not in known:
            known[k] = next(r["parish"] for r in rows
                            if r.get("parish") and _key(r["parish"]) == k)
    return known


def _parish_name(p, known):
    """The known spelling of parish `p`, else `p` as written."""
    k = _key(p)
    if k in known:
        return known[k]
    if k.endswith("s") and k[:-1] in known:            # Källeryds -> Källeryd
        return known[k[:-1]]
    return p


def _join_spellings(rows, known):
    """Every row's parish in its known spelling."""
    for r in rows:
        if r.get("parish"):
            r["parish"] = _parish_name(r["parish"], known)


def _codes_and_parishes(rows):
    """parish -> its archive codes, and archive code -> its parishes."""
    code_of, parish_of = {}, {}
    for r in rows:
        if r.get("archive_code") and r.get("parish"):
            code_of.setdefault(r["parish"], set()).add(r["archive_code"])
            parish_of.setdefault(r["archive_code"], set()).add(r["parish"])
    return code_of, parish_of


def _parishes_from_codes(rows, parish_of):
    """A reference led by its code names no parish: the code's one parish."""
    for r in rows:
        if r.get("archive_code") and not r.get("parish") \
                and len(parish_of.get(r["archive_code"], ())) == 1:
            r["parish"] = next(iter(parish_of[r["archive_code"]]))


def _volumes_from_images(rows):
    """An ra-link row takes the volume of an ra-full row with the same image."""
    by_image = {}
    for r in rows:
        if r.get("tier") == "ra-full" and r.get("image_id"):
            by_image[r["image_id"]] = {k: r[k] for k in
                                       ("parish", "archive_code", "series", "vol", "years")}
    for r in rows:
        if r.get("tier") == "ra-link" and r.get("image_id") in by_image:
            r.update(by_image[r["image_id"]])
            r["vol_from_image"] = "yes"


def _codes_from_parishes(rows, code_of):
    """A row with a parish and no archive code takes the parish's first code."""
    for r in rows:
        if r.get("parish") and not r.get("archive_code") and r["parish"] in code_of:
            r["archive_code"] = sorted(code_of[r["parish"]])[0]


def _places_from_plac(rows, known, reference):
    """Parish, farm and detail from PLAC ("Sörgården, Göhestra, Hagelstorp,
    Källeryd, Jönköpings län") as plac_* fields; the parish and farm of a
    plac-only row."""
    from sg.records import gazetteer
    from sg.records import parish_names
    plain = {_key(p): p for p in known.values()}
    towns = _towns_per_parish(rows)
    names = parish_names.load() if reference is None else reference
    places = _PlaceReader(plain, names)
    places.add_written_parishes(rows)
    for r in rows:
        parts = gazetteer.plac_parts(r.get("event_place"))
        i, name = places.parish_at(parts)
        if i is not None:
            r.setdefault("plac_parish", name)
            _set_plac_farm(r, parts, i, towns.get(_key(name), ()), names)
        if r.get("tier") == "plac-only":
            r["parish"] = r.get("plac_parish", "")
            r["farm"] = r.get("plac_farm", "")


def _towns_per_parish(rows):
    """parish key -> keys of the towns its records name before it."""
    # towns that records name before a congregation ("Sigtuna, Sankt Olof
    # och Sankt Per"): in a PLAC the town sits between farm and parish
    towns = {}
    for r in rows:
        if r.get("town") and r.get("parish"):
            towns.setdefault(_key(r["parish"]), set()).add(_key(r["town"]))
    return towns


def _set_plac_farm(r, parts, i, towns_here, names):
    """plac_farm and plac_detail: the parts before the parish at parts[i]
    (and before a town named with it)."""
    from sg.records import gazetteer
    # the part next to the parish is usually the village (by);
    # anything before it is a farm or house within it
    j = i - 1 if i and _key(parts[i - 1]) in towns_here else i
    farm = gazetteer.drop_county_code(parts[j - 1]) if j else ""   # "Västra Hult (K)"
    if farm and names.is_town(farm):
        farm = ""                 # a town, not a farm ("Göteborg, Göteborgs Karl Johan");
                                  # a farm may share a parish's name ("Ekeby, Storsocken")
    r.setdefault("plac_farm", farm)
    r.setdefault("plac_detail", ", ".join(parts[:j - 1]) if j > 1 else "")


def _family_groups(plain, names):
    """Which parish groups of the full list the family's own names stand for
    ("Norrköpings Östra Eneby" -> the group that "Östra Eneby" also names)."""
    family_of = {}
    for name in plain.values():
        for g in names.candidates(name):
            family_of.setdefault(g, name)
    return family_of


def _region(p):
    """County, province or country: "Älvsborg", "Alvsborg", "Goteborg Bohus"."""
    from sg.records import gazetteer
    from sg.records import parish_names
    return gazetteer.region(p) or gazetteer.region(p.strip() + "s") \
        or bool(parish_names.counties_of(p))


def _explicit_parish(part):
    """A part written as a parish ("Västerlanda förs.") whose name reads
    as a name: capitalised, with no move word left in it."""
    from sg.records import gazetteer
    part = gazetteer.drop_county_code(part)
    if not EXPLICIT_PARISH.search(part):
        return ""
    name = degenitive(EXPLICIT_PARISH.sub("", part).strip())      # "Okändhems socken"
    words = [w for w in name.split() if w.lower() != "och"]
    if not words or not all(re.match(r"[A-ZÅÄÖÉ]|S:t", w) for w in words):
        return ""                  # "till Maria", "Byns fattigstuga Torps"
    return name


def _up_to_country(parts):
    """The parts up to and including a country, if one is named."""
    from sg.records import gazetteer
    country = next((i for i, p in enumerate(parts)
                    if p.strip(" .").lower() in gazetteer.COUNTRIES), None)
    if country is not None:
        parts = parts[:country + 1]
    return parts


def _before_regions(parts):
    """Where the trailing counties, provinces and countries start (one part
    is always kept)."""
    end = len(parts)
    while end > 1 and _region(parts[end - 1]):
        end -= 1
    return end


class _PlaceReader:
    """Finds the parish among a PLAC's parts: by the names the family's
    citations use (`plain`, key -> name), else by the full parish list."""

    def __init__(self, plain, names):
        self.plain, self.names = plain, names
        self.family_of = _family_groups(plain, names)

    def part_key(self, part):
        """The part's key, without a parish suffix or a genitive s."""
        from sg.records import gazetteer
        k = _key(PLAC_SUFFIX.sub("", gazetteer.drop_county_code(part)))
        if k not in self.plain and k.endswith("s") and k[:-1] in self.plain:
            k = k[:-1]                                      # "Båraryds kyrka"
        return k

    def add_written_parishes(self, rows):
        """Parishes written as such that neither list knows join the family's."""
        from sg.records import gazetteer
        # Parishes written as such ("Kyrkeby, Västerlanda förs., Fuxerna") count
        # for every row, whichever comes first; one the full list knows by
        # another spelling keeps that spelling.
        for r in rows:
            parts = gazetteer.plac_parts(r.get("event_place"))
            for i, part in enumerate(parts):
                name = _explicit_parish(part)
                if name and not self.lookup(i, parts)[0]:
                    self.plain.setdefault(_key(name), name)

    def lookup(self, i, parts):
        """(parish name or None, how) for parts[i]: a name the family's
        citations use, else the full parish list, narrowed by the other
        parts (a county, a town). Ambiguous names give None."""
        from sg.records import gazetteer
        part = parts[i]
        k = self.part_key(part)
        if k in self.plain:
            return self.plain[k], "family"
        others = parts[:i] + parts[i + 1:]
        counties = [p for p in others if _region(p)]
        if not (counties or len(parts) > 1 or PLAC_SUFFIX.search(gazetteer.drop_county_code(part))):
            # a lone name ("Högalid"): more likely the family's own farm
            # (the gazetteer's unique village) than a namesake parish
            return None, "lone name"
        return self._from_list(part, counties, others)

    def _from_list(self, part, counties, others):
        """(parish name or None, how) for a part by the full parish list; a
        group the family's names stand for wins."""
        cands = self.names.candidates(part, counties=counties, towns=others)
        if not cands:
            return None, ""
        fam = {self.family_of[g] for g in cands if g in self.family_of}
        if len(fam) == 1:
            return fam.pop(), "parish list, family name"
        if len(cands) == 1:
            return self.names.label(next(iter(cands))), "parish list"
        return self._exact(part, cands)

    def _exact(self, part, cands):
        """(name or None, how): the one candidate whose bare name is the part's."""
        from sg.records import gazetteer
        from sg.records import parish_names
        want = gazetteer.fold(parish_names.degenitive(parish_names.bare(part)))
        exact = [g for g in cands if gazetteer.fold(self.names._base_label(g)) == want]
        if len(exact) == 1:
            return self.names.label(exact[0]), "parish list"
        return None, "ambiguous"

    def parish_at(self, parts):
        """(index, name) of the parish among the parts, or (None, None). Rules:
        docs/records.md, "Reading place strings".
        """
        near = _up_to_country(parts)
        end = _before_regions(near)
        return self._written(near, end) or self._named(near, end) \
            or self._anywhere(parts) or (None, None)

    def _written(self, parts, end):
        """(index, name) of the last part written as a parish, or None."""
        for i in reversed(range(end)):
            if _explicit_parish(parts[i]):
                return i, self.lookup(i, parts)[0] or _explicit_parish(parts[i])
        return None

    def _named(self, parts, end):
        """(index, name) of the last part that names a parish, or None."""
        for i in reversed(range(end)):
            name = self.lookup(i, parts)[0]
            if name:
                # "Haurida, Aneby, Jönköpings län": a modern kommun after a
                # parish, as MyHeritage writes it, or a town ("Västra
                # Vemmenhög, Malmö"); a kommun that is a parish the family's
                # citations name stays ("Åryd, Ödeshög": a village in Ödeshög)
                yields = self._yields(parts[i])
                if i and yields and self.lookup(i - 1, parts)[0]:
                    return i - 1, self.lookup(i - 1, parts)[0]
                return i, name
        return None

    def _yields(self, part):
        """A town or kommun the family's citations do not name as a parish."""
        return (self.names.is_town(part) or self.names.is_kommun(part)) \
            and self.part_key(part) not in self.plain

    def _anywhere(self, parts):
        """(index, name) of the first part that names a parish, counties and
        all, or None."""
        for i in range(len(parts)):
            name = self.lookup(i, parts)[0]
            if name:
                return i, name
        return None


def mark_cited_residences(rows):
    """MyHeritage puts a household record's citation on the person, not on
    the residence event it adds ("Hemvist: Mellan 1863 och 1879 - Stommen,
    Fuxerna" beside RESI BET 1863 AND 1879, Stommen): a residence event of
    the same person, years and place as a record citation gets that
    citation in `cited_as` ("Fuxerna A I/7 p. 78"), so it is not listed as
    uncited. The event row itself stays as it is."""
    cited = {}
    for r in rows:
        if r.get("tier") in ("mh-record", "ra-full", "ra-link") and r.get("series") and r.get("years"):
            label = f"{volume_key(r)} p. {r['page']}" if r.get("page") else volume_key(r)
            for place in {r.get("place_id"), _key(r.get("farm"))} - {None, ""}:
                cited.setdefault((r["person"], r["years"], place), label)
    for r in rows:
        if r.get("tier") != "plac-only" or r.get("event") != "residence":
            continue
        m = re.fullmatch(r"\s*(?:BET|FROM)\s+(\d{4})\s+(?:AND|TO)\s+(\d{4})\s*", r.get("event_date") or "")
        if not m:
            continue
        for place in (r.get("place_id"), _key(r.get("farm"))):
            hit = place and cited.get((r["person"], f"{m[1]}-{m[2]}", place))
            if hit:
                r["cited_as"] = hit
                break


CITE_RANK = {"ra-full": 0, "ra-link": 1, "mh-record": 2}   # which form of a citation leads


def mark_same_citations(rows, pages):
    """One entry cited more than once (MyHeritage's Swedish and English
    copies of a record, a raw Riksarkivet citation added beside the
    MyHeritage record): every copy but the lead gets `same_as`, the lead
    as text ("ra-full Gränna A II a/11 p. 855 bild 431 (person)"). Copies
    are one person on one image: a page mapped to its image by
    Riksarkivet's labels (`pages`, riksarkivet.shelf_pages), else the same
    volume and page. The lead is the strongest form (CITE_RANK), then one
    with a page. Nothing is merged: MyHeritage stays the master."""
    groups = defaultdict(list)
    for r in rows:
        if r.get("tier") in CITE_RANK and r.get("volume"):
            groups[_cited_entry(r, pages)].append(r)
    for (_, _, img), g in groups.items():
        if len(g) < 2:
            continue
        lead = min(g, key=lambda r: (CITE_RANK[r["tier"]], not r.get("page")))
        label = f"{lead['tier']} {lead['volume']}" + (f" p. {lead['page']}" if lead.get("page") else "") \
            + (f" bild {img}" if isinstance(img, int) else "") + f" ({lead['event']})"
        for r in g:
            if r is not lead:
                r["same_as"] = label


def _cited_entry(r, pages):
    """(person, image series, image) when the image is known, else
    (person, volume, page)."""
    series = r.get("ra_images") or ""
    img = r.get("image_no") if series and r.get("image_id") == series else ""
    if not img and series and str(r.get("page", "")).isdigit():
        img = pages.get(series, {}).get(int(r["page"]))
    if img:
        return (r["person"], series, int(img))
    return (r["person"], r["volume"], r.get("page", ""))


def volume_key(r):
    if r.get("series") and r.get("vol"):
        return f"{r['parish']} {r['series']}/{r['vol']}"    # "A II a/3", never "A II a 3"
    if r.get("image_id"):
        return f"{r.get('parish') or '?'} image {r['image_id']}"
    return ""


# -- parishes on Wikidata ----------------------------------------------------------

def resolve_parishes(wd, rows):
    """parish name -> dict(qid, label, code, lat, lon, harad, status)."""
    out = {}
    names = sorted({r["parish"] for r in rows if r.get("parish")})
    codes = defaultdict(set)
    for r in rows:
        if r.get("parish") and r.get("archive_code"):
            codes[r["parish"]].add(r["archive_code"])
    for name in names:
        info = dict(qid="", label="", code=" ".join(sorted(codes[name])),
                    lat=None, lon=None, harad="", status="")
        try:
            items = []
            for code in sorted(codes[name]):
                items += places.items_for_code(wd, code)
            if items:
                info["status"] = "archive code"
            else:
                cands = [p for p in places.candidates(wd, name)
                         if p["kind"] == "församling" and p["archive"]
                         and _key(p["label"]).startswith(_key(name))]
                items = [p["id"] for p in cands]
                info["status"] = ("name" if len(items) == 1 else
                                  f"ambiguous: {len(items)}" if items else "not found")
                if len(items) == 1:
                    info["code"] = " ".join(cands[0]["archive"])
            if items:
                p = places.parish(wd, items[0])
                info.update(qid=p["id"], label=p["label"])
                e = wd.entity(items[0])
                coord = places._claims(e, "P625")
                # a church parish often lacks coordinates: try its predecessor socken
                if not coord:
                    for link in p["replaces"]:
                        if link["item"]:
                            se = wd.entity(link["item"])
                            coord = places._claims(se, "P625")
                            h = places._claims(se, "P131")
                            if h and not info["harad"]:
                                info["harad"] = wd.label(h[0][0])
                            if coord:
                                break
                if coord and isinstance(coord[0][0], dict):
                    info["lat"], info["lon"] = coord[0][0]["latitude"], coord[0][0]["longitude"]
        except Exception as ex:                    # network trouble: keep going
            info["status"] = f"error: {ex.__class__.__name__}"
        out[name] = info
    return out


# -- views ---------------------------------------------------------------------------

RESTORE = ("parish", "series", "vol", "vol_suffix", "years", "page", "row", "farm")


def restore_labels(rows, earlier, extra_parishes=()):
    """MyHeritage's raw exports can damage a record's volume label ("Bok:
    andPlatsLundkvistr"). The same record (same MyHeritage item id) in an
    older export may still carry it intact: copy the volume fields from
    there. The row says which file it came from (restored_from)."""
    good = {}
    for path in earlier:
        for r in normalise(extract(gedcom_io.parse(path, keep_unlinked=True)), extra_parishes):
            if r.get("mh_item") and r.get("tier") == "mh-record" and r.get("vol"):
                good.setdefault(r["mh_item"], (r, path.name))
    n = 0
    for r in rows:
        if r.get("tier") in ("mh-index", "other") and r.get("mh_item") in good:
            old, name = good[r["mh_item"]]
            r.update({k: old.get(k, "") for k in RESTORE}, tier="mh-record", restored_from=name)
            n += 1
    return n


def build(tree, proband, records, wd=None, extra_parishes=(), ra=None, earlier=()):
    rows = normalise(extract(records), extra_parishes)
    if earlier:
        n = restore_labels(rows, earlier, extra_parishes)
        print(f"volume labels restored from earlier exports: {n}")
    kin = lineage.kinship(tree, proband)
    for r in rows:
        k = kin.get(r["person"], ("unlinked", "", ""))
        r["kin"], r["branch"], r["lineage"] = k
        r["label"] = tree.label(r["person"]) if r["person"] in tree.people else r["person"]
        r["volume"] = volume_key(r)
    parishes = resolve_parishes(wd, rows) if wd else {}
    if ra is not None:
        print(f"bare image links given a volume: {image_volumes(ra, rows)} image series")
        attach_volumes(ra, rows, parishes)
    return rows, parishes


# The series an event is recorded in, for finding the volume of a bare
# image link: births in C, deaths in F, marriages in E, the rest in the
# household examinations.
def image_volumes(ra, rows, offline=False):
    """Volumes for bare image links (tier ra-link, no volume): the archives
    of the parish the event's place names, and of the parish of record,
    each searched through its inventory; Riksarkivet's volume record must
    list the very image series (riksarkivet.image_volume). Rows get
    archive_code, series, vol, years and vol_from_image "riksarkivet".
    Returns the number of image series found."""
    from sg.records import parish_names
    names = parish_names.load()
    codes = defaultdict(set)
    for r in rows:
        if r.get("archive_code") and r.get("parish"):
            codes[r["parish"]].add(r["archive_code"])

    def archives(parish):
        out = list(codes.get(parish, ()))
        for g in names.candidates(parish):
            out += [names.items[q]["archive"] for q in names.members(g) if names.items[q].get("archive")]
        if not out:
            try:
                out = ra.archive_codes(parish, offline=offline)
            except RuntimeError:
                out = []
        return list(dict.fromkeys(out))

    todo = defaultdict(list)
    for r in rows:
        if r.get("tier") == "ra-link" and r.get("image_id") and not r.get("vol"):
            todo[r["image_id"]].append(r)
    found = 0
    for image, rs in todo.items():
        parishes = list(dict.fromkeys(p for r in rs for p in (r.get("parish"), r.get("plac_parish")) if p))
        v = None
        for p in parishes:
            try:
                v = ra.image_volume(image, archives(p), offline=offline)
            except RuntimeError:
                v = None
            if v:
                break
        if not v:
            continue
        found += 1
        archive = "/".join(v["code"].split("/")[:3])
        ser, vol = v["code"].split("/")[3:5]
        for r in rs:
            r.update(archive_code=archive, series=ser, vol=vol,
                     years=(v.get("years") or "").replace("–", "-"), vol_from_image="riksarkivet")
            if not r.get("parish"):
                r["parish"] = next((p for p in parishes if archive in archives(p)), "")
            r["volume"] = volume_key(r)
    return found


def attach_volumes(ra, rows, parishes):
    """Give each volume its reference code and Riksarkivet's own facts.

    The parish archive code comes from the tree's tidied citations (exact)
    or, failing that, from a Wikidata match that was unique. Rows get
    ra_code, ra_years, ra_note, ra_viewer, ra_nad (the volume's page in
    Riksarkivet's catalogue), ra_pages (the page span its note gives) and
    ra_image_count; a cited image (bildid) from
    another image series than the volume's is flagged as a conflict."""
    code_of, how = {}, {}
    for r in rows:
        if r.get("archive_code") and r.get("parish"):
            code_of.setdefault(r["parish"], Counter())[r["archive_code"]] += 1
            how[r["parish"]] = "tree citation"
    by_name = {}
    for name in sorted({r["parish"] for r in rows if r.get("series") and r.get("parish")}):
        try:
            by_name[name] = ra.archive_codes(name)
        except RuntimeError:
            by_name[name] = []
        if name not in code_of and len(by_name[name]) == 1:
            code_of[name], how[name] = Counter({by_name[name][0]: 1}), "Riksarkivet, by name"
    for name, info in parishes.items():
        if name not in code_of and info.get("code") and " " not in info["code"] \
                and info.get("status") in ("archive code", "name"):
            code_of[name], how[name] = Counter({info["code"]: 1}), "Wikidata"
    for r in rows:
        own = r.get("archive_code") if r.get("parish") not in code_of else ""
        if not (r.get("series") and r.get("vol") and (own or r.get("parish") in code_of)):
            continue
        archive = own or code_of[r["parish"]].most_common(1)[0][0]
        code = riksarkivet.refcode(archive, r["series"], r["vol"])
        r["ra_code"], r["code_from"] = code, "the reference's own code" if own else how[r["parish"]]
        if by_name.get(r["parish"]) and archive not in by_name[r["parish"]]:
            r["conflict"] = ((r.get("conflict") or "") + f" archive {archive} differs from "
                             f"Riksarkivet's {'/'.join(by_name[r['parish']])} for this name").strip()
        r["series_name"] = riksarkivet.series_name(r["series"])
        try:
            v = ra.volume(code)
            if v is None and (v := ra.resolve(code)):       # a code damaged in copying
                r["ra_code"], r["code_from"] = v["code"], r["code_from"] + f", read as {v['code']}"
            n_img = ra.image_count(v) if v else None
        except RuntimeError:
            r["ra_status"] = "unreachable"
            continue
        if v is None:
            r["ra_status"] = "no such volume at Riksarkivet"
            continue
        r.update(ra_years=v["years"], ra_note=v["note"], ra_viewer=v["viewer"],
                 ra_images=v["images"], ra_nad=v.get("nad", ""), ra_pages=v.get("pages", ""),
                 ra_image_count=n_img or "", ra_status="found")
        if r.get("image_id") and v["images"] and r["image_id"] != v["images"]:
            r["conflict"] = ((r.get("conflict") or "") +
                             f" bildid {r['image_id']} is not this volume's current image series "
                             f"({v['images']}): an older scan, or another volume").strip()
    for r in rows:              # an image count fetched on a later row of the same volume
        if r.get("ra_status") == "found" and not r.get("ra_image_count"):
            r["ra_image_count"] = (ra.cache.get(r["ra_code"]) or {}).get("image_count", "")


def tier_table(rows):
    t = defaultdict(Counter)
    for r in rows:
        if r.get("parish"):
            t[r["parish"]][r["tier"]] += 1
    return t


TIERS = ["ra-full", "ra-link", "mh-record", "mh-index", "tree", "plac-only", "other"]
KINS = ["self", "ancestor", "relative", "spouse of relative", "unlinked"]


def write_csv(rows, path):
    cols = ["person", "label", "kin", "branch", "lineage", "event", "event_date",
            "event_place", "tier", "resourced", "source", "source_title", "parish",
            "archive_code", "series", "vol", "vol_suffix", "volume", "years", "page",
            "row", "farm", "born", "plac_detail", "image_id", "image_no", "vol_from_image", "restored_from", "mh_volume", "conflict", "same_as", "place_id", "place", "village",
            "place_from", "notes", "errata", "mh_id", "ra_code", "code_from", "series_name", "ra_years",
            "ra_note", "ra_viewer", "ra_images", "ra_nad", "ra_pages", "ra_image_count", "ra_status", "mh_collection",
            "mh_item", "cite_date", "url", "cited_as", "mh_label", "ref_format", "ref_in",
            "aid", "ref_text"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# -- command line ----------------------------------------------------------------------

def run(cfg, wikidata=False, gazetteer=None, riksarkivet_lookups=True):
    """The whole pipeline on the configured tree: citations -> volumes ->
    Riksarkivet facts -> gazetteer places -> errata. Returns (rows,
    parishes for display, errata report). Caches are public, in gazetteer/cache/."""
    from sg.common import config
    from sg.records import errata
    from sg.records import gazetteer as gz
    g = cfg.get("gedcom") or {}
    records = gedcom_io.parse(config.path(cfg, g["file"]), **gedcom_io.options(cfg))
    tree = gedcom_io.Tree(config.path(cfg, g["file"]), **gedcom_io.options(cfg))
    proband = g.get("proband")
    gaz = gazetteer or gz.load(cfg)
    gz.CACHE.mkdir(parents=True, exist_ok=True)
    wd = places.Wikidata(gz.CACHE / "wikidata.json") if wikidata else None
    ra = riksarkivet.Riksarkivet(gz.CACHE / "riksarkivet.json") if riksarkivet_lookups else None
    extra = list((cfg.get("volumes") or {}).get("parishes", [])) + list(gaz.parishes)
    for p in gaz.parishes.values():
        extra += p.get("aliases", [])
    try:
        rows, parishes = build(tree, proband, records, wd, extra, ra, earlier=[
            config.path(cfg, f) for f in g.get("earlier", [])])
    finally:
        if wd:
            wd.save()
        if ra:
            ra.save()
    mh = {i: identity.mh_id(p["facts"]) or "" for i, p in tree.people.items()}
    # A tidied Riksarkivet citation names no farm; MyHeritage's reading of
    # the same page does (same person first, else anyone on that page).
    farm_at = {}
    for r in rows:
        if r.get("farm") and r.get("volume") and r.get("page"):
            farm_at.setdefault((r["person"], r["volume"], r["page"]), r["farm"])
            farm_at.setdefault((None, r["volume"], r["page"]), r["farm"])
    for r in rows:
        if not r.get("farm") and r.get("volume") and r.get("page"):
            r["farm"] = farm_at.get((r["person"], r["volume"], r["page"])) \
                or farm_at.get((None, r["volume"], r["page"]), "")
    for r in rows:
        r["mh_id"] = mh.get(r["person"], "")
        canon = gaz.parish(r.get("parish") or "")
        if canon:
            r["parish"] = canon
        pid, how = gaz.resolve(r.get("parish"), r.get("farm"), raw=r.get("event_place"))
        if not pid and r.get("event_place"):
            # the whole string: "Mjölarp, Knekttorpet No 19, Adelöv" -> Mjölarp;
            # "Hagelstorp, Jönköpings län": no parish written, but a village
            # name that occurs in one parish only is unambiguous
            whole, how, _, part = gaz.explain_plac(r["event_place"])
            pid = whole if whole and not whole.startswith("parish:") else None
            if pid and how == "unique village name":
                if r.get("parish") and gaz.parish(r["parish"]) != gaz.places[pid]["parish"]:
                    pid = None                     # a namesake in another parish
                elif not r.get("parish"):
                    r["parish"] = gaz.places[pid]["parish"]
                    r["farm"] = r.get("farm") or part
            elif pid:
                how = "gazetteer" if how != "plac_map" else how
        if pid and how == "plac_map" and gaz.places.get(pid, {}).get("parish"):
            # an override can move a place to the neighbouring parish
            # (a farm written under Gränna that lies in Adelöv)
            r["parish"] = gaz.places[pid]["parish"]
        if pid:
            r["place_id"], r["place"], r["place_from"] = pid, gaz.label(pid), how
            within = gaz.places.get(pid, {}).get("within")
            r["village"] = gaz.label(within) if within else r["place"]
    report = errata.apply(rows, errata.load(config.path(cfg, "errata.toml")))
    mark_cited_residences(rows)
    for r in rows:                       # errata can move a row to another place
        if r.get("place_id") and r["place_id"] in gaz.places and not r.get("place"):
            r["place"] = gaz.label(r["place_id"])
        c = gaz.coords(r["place_id"]) if r.get("place_id") else None
        if c and c[2] != "parish":             # a point of its own (farm, village, ...)
            r["lat"], r["lon"], r["lv"] = round(c[0], 5), round(c[1], 5), c[2]
        r["volume"] = volume_key(r) if r.get("tier") != "plac-only" else ""
        for k in ("notes", "errata"):
            if isinstance(r.get(k), list):
                r[k] = " | ".join(r[k])
    mark_same_citations(rows, riksarkivet.shelf_pages(Path(cfg["data_dir"]) / "archive"))
    display = {}
    for name, p in gaz.parishes.items():
        display[name] = dict(code=p.get("archive", ""), qid=p.get("wikidata", ""),
                             label=p.get("label", ""), lat=p.get("lat"), lon=p.get("lon"),
                             harad=p.get("harad", ""), status=p.get("archive_from", ""))
    for name, info in parishes.items():
        display.setdefault(name, info)
    return rows, display, report


def _main(argv):
    from sg.common import config
    from sg.records import errata
    bad = [a for a in argv if a.startswith("--") and a not in ("--wikidata", "--no-riksarkivet")]
    if bad:
        raise SystemExit(f"unknown option {' '.join(bad)}; known: --wikidata --no-riksarkivet")
    cfg = config.load()
    rows, parishes, report = run(cfg, wikidata="--wikidata" in argv,
                                 riksarkivet_lookups="--no-riksarkivet" not in argv)
    argv = [a for a in argv if not a.startswith("--")]
    g = cfg.get("gedcom") or {}
    if argv and argv[0] == "farm":
        homes.print_farms(rows, " ".join(argv[1:]))
        return
    if argv and argv[0] == "home":
        homes.print_homes(cfg, rows, " ".join(argv[1:]), offline="--no-riksarkivet" in sys.argv)
        return
    write_csv(rows, config.path(cfg, "volume_refs.csv"))
    archivesview.write(rows, parishes, config.path(cfg, "archives.html"), g.get("proband", ""))
    errata.write_report(config.path(cfg, "errata_report.md"), report)
    st = Counter(x[1] for x in report)
    if report:
        print("errata: " + ", ".join(f"{k} {v}" for k, v in st.items())
              + " (data/output/errata_report.md)")
    placed = sum(1 for r in rows if r.get("place_id"))
    with_farm = sum(1 for r in rows if r.get("farm"))
    print(f"places: {placed} of {with_farm} rows with a farm/village resolve to the gazetteer")
    tiers = Counter(r["tier"] for r in rows)
    print(f"{len(rows)} rows: " + ", ".join(f"{t} {tiers[t]}" for t in TIERS if tiers[t]))
    vols = Counter(r["volume"] for r in rows if r["volume"])
    print(f"{len(vols)} volumes in {len({r['parish'] for r in rows if r['volume']})} parishes")
    unres = Counter(r["volume"] for r in rows if r["tier"] == "ra-link" and not r.get("vol_from_image"))
    if unres:
        print(f"{sum(unres.values())} Riksarkivet links in {len(unres)} image series "
              "with no full citation to name their volume")
    print("wrote volume_refs.csv and archives.html")


if __name__ == "__main__":
    _main(sys.argv[1:])
