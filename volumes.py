"""
The research as it sits in the record volumes: which parish books, pages
and farms the tree's citations point at, and who on those pages is family.

Household-examination books (husförhörslängder, församlingsböcker) are
ordered by village and farm, so a farm occupies a page range in each
volume. Seen per volume, the cited pages show where the family's farms
sit in the book, which neighbouring pages hold relatives, and which pages
are cited only for in-laws or people not linked to us.

Every citation is reduced to one shape, whatever its tidiness:

    tier      ra-full    Riksarkivet citation: archive, SE/... code,
                         series/volume, years, bildid, sida
              ra-link    only a bildvisning URL (volume image id + image);
                         the volume is resolved through ra-full citations
                         sharing the image id, if any
              mh-record  MyHeritage household-examination record match
                         ("Bok: ...Källeryd AIIa2, 1906 - 1921 ... Sida:35
                         ... Rad:8"); `resourced` if its source has
                         already been renamed to a parish archive
              mh-index   other MyHeritage record collections (baptisms,
                         marriages, censuses): a record, but no volume
              tree       other people's trees and web sites
              plac-only  an event with a place and no citation at all

An Arkiv Digital reference with its volume ("Socken AI:7 (1821-1831) Bild 261 /
sid 509 (AID: ..., NAD: SE/...)") counts as ra-full: it names the volume as
fully as a Riksarkivet citation. `ref_format` says which reader read a row.

Volumes are keyed (parish, series, volume): MyHeritage's "AIIa2" and
Riksarkivet's "A II a/2" are the same book. Parish names are joined by
spelling: "Källeryds kyrkoarkiv" -> "Källeryd" when that name occurs in
the MyHeritage citations (heuristic).

Each cited person is classed against the proband: ancestor (with lineage
code), relative (closest shared ancestors' branch FF/FM/MF/MM), spouse of
a relative, or unlinked.

Parishes are resolved to Wikidata items (places.py) by archive code
first, then by name among church parishes holding an archive code. Name
matches are candidates; ambiguous ones are listed, not chosen.

Sketch status (unvalidated): written against one Gramps export of a
MyHeritage tree. MyHeritage page and row numbers are its indexers'
reading; Riksarkivet "sida" is the book's own page, not the image number.
Parishes cited only as places (no volume yet) can be named in
family.toml: `[volumes] parishes = ["..."]`. The references themselves are read
by references.py (Riksarkivet, Arkiv Digital, MyHeritage labels, image
links), in source citations and also in notes, addresses and event values
(`ref_in`). Not handled: Sveriges dödbok, the volume suffix
in "Källeryd_AIIa3-296" (kept as written), farm names' spelling variants.

    python volumes.py                 # report + HTML in data/
    python volumes.py --wikidata      # also resolve parishes by name on Wikidata (slow)
    python volumes.py --no-riksarkivet  # skip volume lookups (riksarkivet.py)
    python volumes.py farm Hagelstorp # one farm across volumes, as text
"""
import csv
import html
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict

import gedcom_io
import identity
import places
import references
import riksarkivet

MH_ITEM = re.compile(r"collection-(?P<coll>\d+)/[^?]*\?(?:[^ ]*&)?itemId=(?P<item>\d+)")
# The reference readers live in references.py; these names stay for callers.
BILD, BILDID, MH_BOK, MH_FIELD = references.BILD, references.BILDID, references.MH_BOK, references.MH_FIELD
HEMVIST = re.compile(r"Hemvist:\s*Mellan\s*(\d{4})\s*och\s*(\d{4})\s*-\s*([^\n]+)")

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
_PARISH_BAD = re.compile(r"Bok|Sweden|Plats|Sida|Län\b|Källa|Provins|Församling|Rad\b|Hemvist")


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
    flat = re.sub(r"<[^>]+>", " ", page_field + "\n" + text)
    c = dict(source=sid, source_title=title, url="", tier="other",
             parish="", archive_code="", series="", vol="", vol_suffix="",
             years="", page="", row="", farm="", image_id="", image_no="",
             mh_collection="", mh_item="", resourced="", ref_format="", ref_in="citation")
    url = re.search(r"https?://\S+", page_field)
    c["url"] = url.group(0) if url else ""

    item = MH_ITEM.search(page_field) or MH_ITEM.search(text)
    if item:
        c["mh_collection"], c["mh_item"] = item["coll"], item["item"]
    mh = {}
    bok = next(iter(references.myheritage(text)), None)
    if bok:
        mh = dict(mh_label=bok["label"], parish=bok.get("parish", ""),
                  town=valid_parish(bok.get("town", "")), series=bok.get("series", ""),
                  vol=bok.get("vol", ""), vol_suffix=bok.get("vol_suffix", ""),
                  years=bok.get("years", ""))
        mh.update({k: bok[k] for k in ("farm", "page", "row") if bok.get(k)})
        # a damaged "Plats" field: take the farm from the residence line, but
        # only when that line names this record's parish after it
        # ("Gården, Sigtuna, Sankt Olof och Sankt Per, ..."), so a line
        # that starts with a parish or town gives no farm
        hv = HEMVIST.search(text)
        if hv and not mh.get("farm"):
            parts = [x.strip() for x in hv[3].split(",")]
            names = {_key(mh["parish"]), _key(mh["town"])} - {""}
            if len(parts) > 1 and _key(parts[0]) not in names and names & {_key(x) for x in parts[1:3]}:
                mh["farm"] = parts[0]
    elif "Bok" in text:              # a label the pattern did not read: kept for tracing
        sq = _squash(text)
        c["mh_label"] = sq[sq.index("Bok"):][:200].split("Se hushåll")[0].strip()

    # A volume reference in the citation text, else in the PAGE (searched
    # apart: joined, the URL would run into the archive name).
    ref = None
    for part in (text, page_field):
        ref = ref or next((r for r in references.find(part, mh=False)
                           if r["format"] != "image"), None)
    bild = BILDID.search(flat) or BILD.search(flat)
    if bild:
        c["image_id"], c["image_no"] = bild["img"], str(int(bild["no"]))
    if ref:
        c.update(tier="ra-full", ref_format=ref["format"], archive_code=ref.get("archive_code", ""),
                 years=ref.get("years", ""), page=ref.get("page", ""),
                 series=ref.get("series", ""), vol=ref.get("vol", ""))
        if ref["format"] == "riksarkivet":
            # "X kyrkoarkiv, Series, Subseries, SE/..." has one field more than
            # the pattern expects: look for the archive name anywhere before it
            m = ARCHIVE_SOURCE.match(ref.get("archive", "")) \
                or re.search(r"(?P<name>[^,>\n]+?)\s+kyrkoarkiv", text) \
                or ARCHIVE_SOURCE.match(title)
            # only a church archive names a parish (not a police or orphanage archive)
            c["parish"] = valid_parish(m["name"].strip()) if m else ""
            c["ra_archive"] = ref.get("archive", "")
        else:                                     # Arkiv Digital: the parish as such
            c["parish"] = valid_parish(ref.get("parish", ""))
            c["aid"] = ref.get("aid", "")
        if mh:
            # a MyHeritage record later tidied with the archive citation:
            # keep the indexer's reading beside it and flag disagreement
            c["farm"], c["row"] = mh.get("farm", ""), mh.get("row", "")
            c["mh_label"] = mh["mh_label"]
            c["mh_volume"] = f"{mh['parish']} {mh['series']} {mh['vol']} ({mh['years']}) p. {mh.get('page', '?')}"
            if (mh["series"], mh["vol"]) != (c["series"], c["vol"]) or \
                    (mh.get("page") and c["page"] and mh["page"] != c["page"]):
                c["conflict"] = "MyHeritage label and archive citation differ"
        return c
    if bild:
        c["tier"], c["ref_format"] = "ra-link", "image"
        m = ARCHIVE_SOURCE.match(title)
        c["parish"] = valid_parish(m["name"] if m else mh.get("parish", ""))
        c["ra_archive"] = title if m else ""
        for k in ("series", "vol", "years", "page", "row", "farm"):
            c[k] = c[k] or mh.get(k, "")
        return c
    if mh:
        mh["parish"] = valid_parish(mh.get("parish"))
        c.update(mh, tier="mh-record", ref_format="myheritage")
        if ARCHIVE_SOURCE.match(title):
            c["resourced"] = title
        return c
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
    return c


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
PLAC_SUFFIX = re.compile(r"\s+(socken|lands- och stadsförsamling|landsförsamling|"
                         r"stadsförsamling|församling|kyrka|lf\.?|sf\.?)$", re.I)


# A part that says it is a parish, known or not ("Västerlanda förs.").
EXPLICIT_PARISH = re.compile(r"\s+(?:förs\.?|församling|socken)$", re.I)


def degenitive(name):
    """Archive names are genitive: "Källeryds kyrkoarkiv", but "Gränna
    kyrkoarkiv", "Linderås kyrkoarkiv". Drop a final s after a consonant
    (heuristic: a parish whose own name ends in consonant + s would lose it)."""
    return re.sub(r"(?<=[b-df-hj-np-tv-zß])s$", "", name.strip())


def normalise(rows, extra_parishes=()):
    """Join parish spellings, resolve ra-link volumes through image ids,
    derive farm and parish from PLAC for uncited events. Parish names come
    from the record citations; `extra_parishes` adds parishes that appear
    only in places (no volume cited yet), so PLAC parsing finds them."""
    for r in rows:                                    # "Källeryds kyrkoarkiv"
        if r.get("tier") in ("ra-full", "ra-link", "other") and r.get("parish") \
                and r.get("ref_format") != "arkivdigital":  # Arkiv Digital: not genitive
            r["parish"] = degenitive(r["parish"])
    mh_names = {_key(r["parish"]): r["parish"] for r in rows
                if r.get("tier") == "mh-record" and r["parish"]}
    archive_names = {_key(r["parish"]) for r in rows
                     if r.get("tier") in ("ra-full", "ra-link") and r.get("parish")}
    known = dict(mh_names)
    for p in extra_parishes:
        known.setdefault(_key(p), unicodedata.normalize("NFC", p))
    for k in archive_names:
        if k not in known:
            known[k] = next(r["parish"] for r in rows
                            if r.get("parish") and _key(r["parish"]) == k)

    def parish_name(p):
        k = _key(p)
        if k in known:
            return known[k]
        if k.endswith("s") and k[:-1] in known:            # Källeryds -> Källeryd
            return known[k[:-1]]
        return p

    code_of, parish_of = {}, {}
    for r in rows:
        if r.get("parish"):
            r["parish"] = parish_name(r["parish"])
        if r.get("archive_code") and r.get("parish"):
            code_of.setdefault(r["parish"], set()).add(r["archive_code"])
            parish_of.setdefault(r["archive_code"], set()).add(r["parish"])
    for r in rows:              # a reference led by its code names no parish
        if r.get("archive_code") and not r.get("parish") \
                and len(parish_of.get(r["archive_code"], ())) == 1:
            r["parish"] = next(iter(parish_of[r["archive_code"]]))
    by_image = {}
    for r in rows:
        if r.get("tier") == "ra-full" and r.get("image_id"):
            by_image[r["image_id"]] = {k: r[k] for k in
                                       ("parish", "archive_code", "series", "vol", "years")}
    for r in rows:
        if r.get("tier") == "ra-link" and r.get("image_id") in by_image:
            r.update(by_image[r["image_id"]])
            r["vol_from_image"] = "yes"
        if r.get("parish") and not r.get("archive_code") and r["parish"] in code_of:
            r["archive_code"] = sorted(code_of[r["parish"]])[0]

    # Places from PLAC: "Sörgården, Göhestra, Hagelstorp, Källeryd, Jönköpings län".
    plain = {_key(p): p for p in known.values()}
    # towns that records name before a congregation ("Sigtuna, Sankt Olof
    # och Sankt Per"): in a PLAC the town sits between farm and parish
    towns = {}
    for r in rows:
        if r.get("town") and r.get("parish"):
            towns.setdefault(_key(r["parish"]), set()).add(_key(r["town"]))
    import gazetteer

    def part_key(part):
        k = _key(PLAC_SUFFIX.sub("", gazetteer.drop_county_code(part)))
        if k not in plain and k.endswith("s") and k[:-1] in plain:
            k = k[:-1]                                      # "Båraryds kyrka"
        return k

    def parish_at(parts):
        """Index of the parish among the parts, or None. A part written as a
        parish ("Västerlanda förs.") wins; otherwise the rightmost known
        parish, once county, province and country are dropped from the end,
        since a farm or village to its left can share a parish's name
        ("Ekeby, Bergshammar, Södermanlands"; "Åryd, Ödeshög"). Without a
        known parish in what is left (a parish named like its county:
        "Kalmar, Sweden"), the first known part from the left, as before.
        Two places run together ("…, Gränna, Jönköpings, Småland, Sweden,
        Adelöv, Jönköping, Sverige") are read up to the first country, as
        before. Not decided by names alone: a modern kommun named like a
        parish ("Båraryd, Gislaved, Jönköpings län") reads as the parish."""
        whole = parts
        country = next((i for i, p in enumerate(parts)
                        if p.strip(" .").lower() in gazetteer.COUNTRIES), None)
        if country is not None:
            parts = parts[:country + 1]
        region = lambda p: gazetteer.region(p) or gazetteer.region(p.strip() + "s")  # "Älvsborg"
        end = len(parts)
        while end > 1 and region(parts[end - 1]):
            end -= 1
        explicit = [i for i in range(end) if EXPLICIT_PARISH.search(parts[i])]
        if explicit:
            return explicit[-1]
        hits = [i for i in range(end) if part_key(parts[i]) in plain]
        if hits:
            return hits[-1]
        return next((i for i, p in enumerate(whole) if part_key(p) in plain), None)

    for r in rows:
        parts = gazetteer.plac_parts(r.get("event_place"))
        i = parish_at(parts)
        if i is not None:
            k = part_key(parts[i])
            if k not in plain:
                # "Kyrkeby, Västerlanda förs., Fuxerna": written as a parish,
                # though no volume of it is cited yet
                plain[k] = EXPLICIT_PARISH.sub("", parts[i]).strip()
            # the part next to the parish is usually the village (by);
            # anything before it is a farm or house within it
            r.setdefault("plac_parish", plain[k])
            j = i - 1 if i and _key(parts[i - 1]) in towns.get(k, ()) else i
            r.setdefault("plac_farm", parts[j - 1] if j else "")
            r.setdefault("plac_detail", ", ".join(parts[:j - 1]) if j > 1 else "")
        if r.get("tier") == "plac-only":
            r["parish"] = r.get("plac_parish", "")
            r["farm"] = r.get("plac_farm", "")
    return rows


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


def volume_key(r):
    if r.get("series") and r.get("vol"):
        return f"{r['parish']} {r['series']}/{r['vol']}"    # "A II a/3", never "A II a 3"
    if r.get("image_id"):
        return f"{r.get('parish') or '?'} image {r['image_id']}"
    return ""


# -- kinship ----------------------------------------------------------------------

def kinship(tree, proband):
    """person -> (class, branch, lineage codes)."""
    P = tree.id(proband)
    out = {}
    anc = {}
    for x, code in tree.ancestors(P):
        anc.setdefault(x, []).append(code)
    for i in tree.people:
        if i == P:
            out[i] = ("self", "", "")
        elif i in anc:
            codes = sorted(anc[i], key=len)
            out[i] = ("ancestor", " ".join(sorted({c[:2] for c in codes})), " ".join(codes))
    for i in tree.people:
        if i in out:
            continue
        rel = tree.relationship(P, i)
        if rel:
            codes = {c for _, c, _ in rel}
            br = " ".join(sorted({c[:2] if len(c) >= 2 else "sib" for c in codes}))
            out[i] = ("relative", br, " ".join(sorted(codes)))
    spouses = defaultdict(set)
    for f in tree.families.values():
        if f["husb"] and f["wife"]:
            spouses[f["husb"]].add(f["wife"])
            spouses[f["wife"]].add(f["husb"])
    for i in tree.people:
        if i in out:
            continue
        kin = [out[s] for s in spouses[i] if s in out]
        if kin:
            out[i] = ("spouse of relative", " ".join(sorted({k[1] for k in kin if k[1]})), "")
        else:
            out[i] = ("unlinked", "", "")
    return out


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
    kin = kinship(tree, proband)
    for r in rows:
        k = kin.get(r["person"], ("unlinked", "", ""))
        r["kin"], r["branch"], r["lineage"] = k
        r["label"] = tree.label(r["person"]) if r["person"] in tree.people else r["person"]
        r["volume"] = volume_key(r)
    parishes = resolve_parishes(wd, rows) if wd else {}
    if ra is not None:
        attach_volumes(ra, rows, parishes)
    return rows, parishes


def attach_volumes(ra, rows, parishes):
    """Give each volume its reference code and Riksarkivet's own facts.

    The parish archive code comes from the tree's tidied citations (exact)
    or, failing that, from a Wikidata match that was unique. Rows get
    ra_code, ra_years, ra_note, ra_viewer; a cited image (bildid) from
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
        except RuntimeError:
            r["ra_status"] = "unreachable"
            continue
        if v is None:
            r["ra_status"] = "no such volume at Riksarkivet"
            continue
        r.update(ra_years=v["years"], ra_note=v["note"], ra_viewer=v["viewer"],
                 ra_images=v["images"], ra_status="found")
        if r.get("image_id") and v["images"] and r["image_id"] != v["images"]:
            r["conflict"] = ((r.get("conflict") or "") +
                             f" bildid {r['image_id']} is not this volume's current image series "
                             f"({v['images']}): an older scan, or another volume").strip()


def tier_table(rows):
    t = defaultdict(Counter)
    for r in rows:
        if r.get("parish"):
            t[r["parish"]][r["tier"]] += 1
    return t


def farm_index(rows):
    """farm -> volume -> sorted pages, with people per page."""
    idx = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        farm = (r.get("place") or r.get("farm") or "").strip()
        if not farm or not r.get("parish"):
            continue
        vol = r["volume"] or f"{r['parish']} (no volume)"
        idx[f"{farm}, {r['parish']}"][vol][r.get("page") or ""].append(r)
    return idx


TIERS = ["ra-full", "ra-link", "mh-record", "mh-index", "tree", "plac-only", "other"]
KINS = ["self", "ancestor", "relative", "spouse of relative", "unlinked"]


def write_csv(rows, path):
    cols = ["person", "label", "kin", "branch", "lineage", "event", "event_date",
            "event_place", "tier", "resourced", "source", "source_title", "parish",
            "archive_code", "series", "vol", "vol_suffix", "volume", "years", "page",
            "row", "farm", "plac_detail", "image_id", "image_no", "vol_from_image", "restored_from", "mh_volume", "conflict", "place_id", "place", "village",
            "place_from", "notes", "errata", "mh_id", "ra_code", "code_from", "series_name", "ra_years",
            "ra_note", "ra_viewer", "ra_images", "ra_status", "mh_collection",
            "mh_item", "cite_date", "url", "cited_as", "mh_label", "ref_format", "ref_in",
            "aid", "ref_text"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_html(rows, parishes, path, proband_label, people=None, paths=None, spouse_of=None,
               view="volumes"):
    """One self-contained page, private (holds names; keep it in data/).
    view="volumes": parishes (map + tidiness), volumes as page strips, farms
    across volumes. view="people": residence timelines and life maps per
    person. Both are written by run(), as volumes.html and people.html."""
    keep = ["person", "label", "kin", "branch", "lineage", "event", "event_date",
            "event_place", "tier", "resourced", "parish", "archive_code", "volume",
            "series", "vol", "years", "page", "row", "farm", "plac_detail", "image_id", "image_no",
            "url", "source_title", "mh_volume", "conflict", "ra_code", "code_from", "series_name",
            "place_id", "place", "village", "place_from", "notes", "errata", "mh_id",
            "ra_years", "ra_note", "ra_viewer", "ra_images", "ra_status", "cited_as"]
    data = [{k: r.get(k, "") or "" for k in keep} for r in rows if r["tier"] != "tree"]
    ppl = []
    people, paths, spouse_of = people or {}, paths or {}, spouse_of or {}
    info = {}
    for r in rows:
        info.setdefault(r["person"], {k: r.get(k, "") for k in ("label", "kin", "branch",
                                                                "lineage", "mh_id")})
    ids = set(people) | {i for i, pts in paths.items() if len(pts) >= 2}
    for i in sorted(ids):
        P = people.get(i) or dict(info.get(i, {}), record=[], documented=[], gaps=[], moves=[],
                                  uncollated=[], born=None, died=None)
        ppl.append({k: P.get(k) for k in ("label", "kin", "branch", "lineage", "mh_id", "born",
                                          "died", "record", "documented", "gaps", "moves")}
                   | dict(id=i, uncollated=len(P.get("uncollated", [])), path=paths.get(i, []),
                          spouses=sorted(s for s in spouse_of.get(i, ()) if s in ids)))
    if view == "people":
        data, parishes = [], {}
    else:
        ppl = []
    payload = json.dumps(dict(rows=data, parishes=parishes, proband=proband_label, people=ppl),
                         ensure_ascii=False, default=str)
    import geoview
    title = "People" if view == "people" else "Record volumes"
    page = (HTML.replace("__DATA__", payload.replace("</", "<\\/"))
            .replace("__VIEW__", "p" if view == "people" else "v")
            .replace("__TITLE__", title).replace("__NAV__", geoview.nav(f"{view}.html")))
    path.write_text(page, encoding="utf-8")


HTML = r"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root{--bg:#fbfaf7;--fg:#1d1c1a;--mut:#6b6760;--line:#dedad2;--card:#fff;
--FF:#2f6db5;--FM:#c0522b;--MF:#2f8f5b;--MM:#8a4fb0;--anc:#111;--sp:#b9a76a;--un:#b8b4ac;--sel:#fff3c4}
@media (prefers-color-scheme:dark){:root{--bg:#171614;--fg:#ece9e2;--mut:#9b968c;--line:#34312c;--card:#201f1c;
--FF:#6ea4e6;--FM:#e8835c;--MF:#5fc38c;--MM:#b98ad8;--anc:#fff;--sp:#9c8d58;--un:#5d5a54;--sel:#4a4220}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,sans-serif}
header{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;gap:16px;flex-wrap:wrap;align-items:center}
h1{font-size:18px;margin:0 12px 0 0}h2{font-size:15px;margin:18px 0 8px}h3{font-size:14px;margin:0}
input,select{font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}
main{display:grid;grid-template-columns:330px 1fr;gap:0;min-height:calc(100vh - 60px)}
@media(max-width:800px){main{grid-template-columns:1fr}}
aside{border-right:1px solid var(--line);padding:12px 16px;overflow:auto;max-height:calc(100vh - 60px);position:sticky;top:0}
section{padding:12px 20px;overflow:auto}
.par{padding:6px 8px;border-radius:6px;cursor:pointer;display:flex;justify-content:space-between;gap:8px}
.par:hover{background:var(--line)}.par.on{background:var(--sel)}
.par small{color:var(--mut)}
.bar{display:flex;height:6px;border-radius:3px;overflow:hidden;margin-top:3px;width:120px}
.t-ra-full{background:#2a7d4f}.t-ra-link{background:#7fbf8f}.t-mh-record{background:#d49a2a}.t-mh-index{background:#e7cf8a}.t-plac-only{background:#bbb}.t-other{background:#ddd}
.legend{display:flex;gap:10px;flex-wrap:wrap;font-size:12px;color:var(--mut)}
.legend span::before{content:"";display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px;background:var(--c)}
.vol{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;margin:10px 0}
.vol .meta{color:var(--mut);font-size:12px;margin:2px 0}
.volno{font-family:ui-monospace,Menlo,monospace;background:var(--line);padding:0 4px;border-radius:4px}
svg text{fill:var(--fg);font-size:10px}
.pages{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}
.pages td{border-top:1px solid var(--line);padding:3px 6px;vertical-align:top}
.pages td:first-child{white-space:nowrap;color:var(--mut);width:70px}
.who{display:inline-block;margin:0 8px 2px 0}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:0}
.tabs button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--fg);padding:4px 12px;cursor:pointer}
.tabs button:first-child{border-radius:6px 0 0 6px}.tabs button:last-child{border-radius:0 6px 6px 0}.tabs button.on{background:var(--sel);font-weight:600}
#lifemap{height:440px;border:1px solid var(--line);border-radius:8px}
#lifebox{margin-bottom:14px}.num{background:none;border:none;box-shadow:none;color:#fff;font-weight:700;font-size:10px}
a.mapbtn{text-decoration:none;display:inline-block}
.mapbtn{font:inherit;font-size:12px;margin-left:6px;padding:1px 8px;border:1px solid var(--line);border-radius:5px;background:var(--card);color:var(--fg);cursor:pointer}
.k-ancestor{font-weight:600}.tag.note{border-color:var(--FM);color:var(--FM)}.k-unlinked{color:var(--mut)}
.tag{font-size:11px;padding:0 5px;border-radius:4px;border:1px solid var(--line);color:var(--mut);margin-left:4px}
a{color:inherit}
#map{width:100%;height:220px;border:1px solid var(--line);border-radius:8px;background:var(--card)}
details summary{cursor:pointer;color:var(--mut)}
.farms td{padding:2px 6px;border-top:1px solid var(--line);vertical-align:top}
</style></head><body>
<header>__NAV__<h1>__TITLE__</h1>
<input id="q" placeholder="Filter: farm, person, volume…" size="28">
<select id="kin"><option value="">all people</option><option value="family">relatives & ancestors</option><option value="ancestor">ancestors only</option></select>
<label class="vonly"><input type="checkbox" id="noplac"> hide uncited places</label>
<div class="legend" id="legend"></div></header>
<main><aside><div id="map"></div><h2>Parishes</h2><div class="legend">
<span style="--c:#2a7d4f">RA full</span><span style="--c:#7fbf8f">RA link</span><span style="--c:#d49a2a">MH record</span><span style="--c:#e7cf8a">MH index</span><span style="--c:#bbb">place only</span></div>
<div id="plist"></div></aside>
<section id="main"></section></main>
<script>
const D=__DATA__;
const BR={FF:'var(--FF)',FM:'var(--FM)',MF:'var(--MF)',MM:'var(--MM)'};
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function color(r){if(r.kin==='self')return 'var(--anc)';if(r.kin==='unlinked')return 'var(--un)';
 if(r.kin==='spouse of relative')return 'var(--sp)';const b=(r.branch||'').split(' ')[0];return BR[b]||'var(--anc)'}
document.getElementById('legend').innerHTML=Object.entries({FF:'FF',FM:'FM',MF:'MF',MM:'MM'}).map(([k,v])=>`<span style="--c:var(--${k})">${v} relative</span>`).join('')+'<span style="--c:var(--sp)">spouse of relative</span><span style="--c:var(--un)">unlinked</span>';
let cur=null;
function filtered(){const q=document.getElementById('q').value.toLowerCase(),k=document.getElementById('kin').value,np=document.getElementById('noplac').checked;
 return D.rows.filter(r=>(!np||r.tier!=='plac-only')&&(!k||(k==='ancestor'?['ancestor','self'].includes(r.kin):['ancestor','self','relative'].includes(r.kin)))
  &&(!q||[r.farm,r.place,r.label,r.volume,r.event_place,r.parish,r.notes].join(' ').toLowerCase().includes(q)))}
function plist(){const rows=filtered(),by={};rows.forEach(r=>{if(!r.parish)return;(by[r.parish]=by[r.parish]||[]).push(r)});
 const T=['ra-full','ra-link','mh-record','mh-index','plac-only','other'];
 const names=Object.keys(by).sort((a,b)=>by[b].length-by[a].length);
 document.getElementById('plist').innerHTML=names.map(n=>{const c={};by[n].forEach(r=>c[r.tier]=(c[r.tier]||0)+1);const tot=by[n].length;
  const p=D.parishes[n]||{};
  return `<div class="par ${n===cur?'on':''}" data-p="${esc(n)}"><div><b>${esc(n)}</b> <small>${esc(p.code||'')}${p.qid?' · '+esc(p.qid):''}</small>
  <div class="bar">${T.filter(t=>c[t]).map(t=>`<div class="t-${t}" style="width:${100*c[t]/tot}%" title="${t}: ${c[t]}"></div>`).join('')}</div></div><small>${tot}</small></div>`}).join('');
 document.querySelectorAll('.par').forEach(e=>e.onclick=()=>{cur=e.dataset.p;go()});
 map(by)}
function map(by){const ps=Object.entries(D.parishes).filter(([n,p])=>p.lat&&by[n]);const el=document.getElementById('map');
 if(!ps.length){el.innerHTML='<p style="padding:8px;color:var(--mut)">No coordinates (run without --no-wikidata).</p>';return}
 const la=ps.map(([,p])=>p.lat),lo=ps.map(([,p])=>p.lon);let [a0,a1,o0,o1]=[Math.min(...la),Math.max(...la),Math.min(...lo),Math.max(...lo)];
 const pad=.15;a0-=pad;a1+=pad;o0-=pad;o1+=pad;const W=300,H=220,k=Math.cos((a0+a1)/2*Math.PI/180);
 const sx=W/((o1-o0)*k),sy=H/(a1-a0),s=Math.min(sx,sy);const X=o=>(o-o0)*k*s+(W-(o1-o0)*k*s)/2,Y=a=>H-((a-a0)*s+(H-(a1-a0)*s)/2);
 el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="100%">${ps.map(([n,p])=>{const r=3+Math.sqrt(by[n].length);
  return `<g data-p="${esc(n)}" style="cursor:pointer"><circle cx="${X(p.lon)}" cy="${Y(p.lat)}" r="${r}" fill="${n===cur?'#d49a2a':'#7a8fa8'}" fill-opacity=".7"><title>${esc(n)} (${by[n].length})</title></circle>
  ${by[n].length>8||n===cur?`<text x="${X(p.lon)+r+2}" y="${Y(p.lat)+3}">${esc(n)}</text>`:''}</g>`}).join('')}</svg>`;
 el.querySelectorAll('g').forEach(g=>g.onclick=()=>{cur=g.dataset.p;go()})}
function who(r){return `<span class="who k-${r.kin.replace(/ /g,'-')}" title="${esc(r.kin)} ${esc(r.lineage||r.branch)} · ${esc(r.event)} ${esc(r.event_date)} · ${esc(r.tier)}${r.resourced?' (re-sourced)':''}"><span class="dot" style="background:${color(r)}"></span>${esc(r.label)}${r.row?` <span class="tag">rad ${esc(r.row)}</span>`:''}${imglink(r)}${r.url?` <a href="${esc(r.url)}" target="_blank" rel="noopener">↗</a>`:''}${r.notes?` <span class="tag note" title="${esc(r.notes)}">note</span>`:''}${r.errata?` <span class="tag note" title="${esc(r.errata)}">corrected</span>`:''}</span>`}
function strip(rows){const pg=rows.map(r=>+r.page).filter(x=>x>0);if(!pg.length)return '';const mx=Math.max(...pg),W=900,H=46;
 const farms={};rows.forEach(r=>{const fn=r.place||r.farm;if(+r.page>0&&fn){const f=farms[fn]=farms[fn]||[1e9,0];f[0]=Math.min(f[0],+r.page);f[1]=Math.max(f[1],+r.page)}});
 const x=p=>8+(W-16)*p/mx;
 return `<svg viewBox="0 0 ${W} ${H+14*Object.keys(farms).length}" width="100%"><line x1="8" x2="${W-8}" y1="20" y2="20" stroke="var(--line)" stroke-width="6"/>
 ${rows.filter(r=>+r.page>0).map(r=>`<line x1="${x(+r.page)}" x2="${x(+r.page)}" y1="10" y2="30" stroke="${color(r)}" stroke-width="2"><title>p. ${esc(r.page)}: ${esc(r.label)} (${esc(r.place||r.farm)})</title></line>`).join('')}
 <text x="8" y="44">1</text><text x="${W-8}" y="44" text-anchor="end">${mx}</text>
 ${Object.entries(farms).sort((a,b)=>a[1][0]-b[1][0]).map(([f,[a,b]],i)=>`<rect x="${x(a)-2}" y="${50+14*i}" width="${Math.max(4,x(b)-x(a)+4)}" height="9" rx="2" fill="#7a8fa8" fill-opacity=".45"/><text x="${x(b)+6}" y="${58+14*i}">${esc(f)} ${a===b?'p. '+a:'pp. '+a+'–'+b}</text>`).join('')}</svg>`}
function volhead(v,rs,yrs){const r=rs.find(x=>x.ra_code)||rs[0];
 if(!r.series||v.startsWith('—'))return `<h3>${esc(v)}</h3>`;
 const ra=rs.find(x=>x.ra_status==='found');const ry=ra?ra.ra_years:'';
 const mhy=[...new Set(rs.filter(x=>x.tier==='mh-record'&&x.years).map(x=>x.years.replace('-','–')))];
 const conf=[...new Set(rs.map(x=>x.conflict).filter(Boolean))];const vn=[...new Set(rs.map(x=>x.notes).filter(Boolean))];
 return `<h3>${esc(r.parish)} · <span class="volno">${esc(r.series)}/${esc(r.vol)}</span>${r.series_name?' · '+esc(r.series_name):''} · ${esc(ry||yrs.replace('-','–'))} <a class="mapbtn" href="geography.html#q=${encodeURIComponent(v)}&layer=record" target="geography">on map</a></h3>
 <div class="meta">${r.ra_code?(ra&&ra.ra_viewer?`<a href="${esc(ra.ra_viewer)}" target="_blank" rel="noopener">${esc(r.ra_code)}</a> (opens the volume at Riksarkivet; code from ${esc(r.code_from)})`:esc(r.ra_code)+' · '+esc(r.ra_status||'not looked up')):'archive code unknown: no tidied citation or unique Wikidata match for this parish'}
 ${ra&&ra.ra_note?`<br>Riksarkivet note: <i>${esc(ra.ra_note)}</i>`:''}
 ${mhy.length&&ry&&mhy.some(y=>y!==ry)?`<br>MyHeritage label years: ${esc(mhy.join(', '))}`:''}
 ${conf.length?`<br><b style="color:var(--FM)">Check: ${esc(conf.join('; '))}</b>`:''}${vn.length?`<br>Notes: ${esc(vn.join(' | '))}`:''}</div>`}
function imglink(r){return r.image_id&&r.image_no?` <a class="tag" href="https://sok.riksarkivet.se/bildvisning/${esc(r.image_id)}_${String(r.image_no).padStart(5,'0')}" target="_blank" rel="noopener">bild ${esc(r.image_no)}</a>`:''}
function render(){plist();const M=document.getElementById('main');const rows=filtered().filter(r=>!cur||r.parish===cur);
 if(!cur&&!document.getElementById('q').value){M.innerHTML='<p>Pick a parish on the left, or filter by a farm or person (e.g. a village name) to see it across all volumes.</p>'+farmsAll(rows);return}
 const vols={};rows.forEach(r=>{const v=r.volume||(r.tier==='plac-only'?'— places without a citation':'— records without a volume');(vols[v]=vols[v]||[]).push(r)});
 const order=Object.keys(vols).sort((a,b)=>{const y=v=>+((vols[v].find(r=>r.years)||{}).years||'9999').slice(0,4);return a.startsWith('—')-b.startsWith('—')||y(a)-y(b)||a.localeCompare(b)});
 const p=D.parishes[cur]||{};
 M.innerHTML=(cur?`<h2>${esc(cur)} <a class="mapbtn" href="geography.html#parish=${encodeURIComponent(cur)}" target="geography">on map</a> <small style="color:var(--mut);font-weight:400">${esc(p.code||'')} ${p.qid?`<a href="https://www.wikidata.org/wiki/${p.qid}" target="_blank">${p.qid}</a> ${esc(p.label)}`:''} ${esc(p.harad||'')} ${p.status?'· '+esc(p.status):''}</small></h2>`:'')
 +order.map(v=>{const rs=vols[v],pages={};rs.forEach(r=>{const k=r.page||'';(pages[k]=pages[k]||[]).push(r)});
  const keys=Object.keys(pages).sort((a,b)=>(+a||1e9)-(+b||1e9));const yrs=(rs.find(r=>r.years)||{}).years||'';
  const tiers=[...new Set(rs.map(r=>r.tier))].join(', ');const fam=rs.filter(r=>['ancestor','relative','self'].includes(r.kin)).length;
  return `<div class="vol">${volhead(v,rs,yrs)}<div class="meta">${rs.length} citations, ${fam} of relatives · ${esc(tiers)}</div>${strip(rs)}
  <table class="pages">${keys.map(k=>{const fs=[...new Set(pages[k].map(r=>r.place&&r.place!==r.farm?r.place+' ('+r.farm+')':r.farm).filter(Boolean))];const seen=new Set();
   return `<tr><td>${k?'p. '+esc(k):(pages[k][0].image_no?'img '+esc(pages[k][0].image_no):'')}</td><td>${fs.length?`<b>${esc(fs.join(' / '))}</b><br>`:''}${pages[k].filter(r=>{const s=r.person+r.event;if(seen.has(s))return false;seen.add(s);return true}).map(who).join('')}</td></tr>`}).join('')}</table></div>`}).join('')}
function farmsAll(rows){const F={};rows.forEach(r=>{const fn=r.place||r.farm;if(!fn||!r.parish||r.cited_as)return;const k=fn+', '+r.parish;(F[k]=F[k]||[]).push(r)});
 const ks=Object.keys(F).sort((a,b)=>F[b].length-F[a].length).slice(0,80);
 return `<h2>Farms and villages, most cited first</h2><table class="farms">${ks.map(k=>{const vs={};F[k].forEach(r=>{const v=r.volume||'(no volume)';(vs[v]=vs[v]||new Set()).add(r.page)});
 const yr=v=>+((F[k].find(r=>(r.volume||'(no volume)')===v&&r.years)||{}).years||'9999').slice(0,4);
 return `<tr><td><b>${esc(k)}</b></td><td>${F[k].length}</td><td>${Object.entries(vs).sort((a,b)=>yr(a[0])-yr(b[0])).map(([v,s])=>esc(v)+(([...s].filter(Boolean).length)?' p. '+[...s].filter(Boolean).sort((a,b)=>a-b).join(', '):'')).join('<br>')}</td></tr>`}).join('')}</table>`}
const view='__VIEW__';
const PAL=['#2f6db5','#c0522b','#2f8f5b','#8a4fb0','#b08a1e','#1f8a96','#a8326b','#5d6b2f'];
const pcol={};const pc=n=>pcol[n]=pcol[n]||PAL[Object.keys(pcol).length%PAL.length];
function people(){const q=document.getElementById('q').value.toLowerCase(),k=document.getElementById('kin').value;
 const rank={self:0,ancestor:1,relative:2,'spouse of relative':3,unlinked:4};
 let ps=(D.people||[]).filter(P=>(!k||(k==='ancestor'?['ancestor','self'].includes(P.kin):['ancestor','self','relative'].includes(P.kin)))
  &&(!q||[P.label,P.mh_id,...P.record.map(s=>s.parish+' '+s.place)].join(' ').toLowerCase().includes(q)));
 ps.sort((a,b)=>rank[a.kin]-rank[b.kin]||b.uncollated-a.uncollated||a.label.localeCompare(b.label));
 const tot=ps.reduce((n,P)=>n+P.uncollated,0),gp=ps.reduce((n,P)=>n+P.gaps.length,0);
 const M=document.getElementById('main');
 M.innerHTML=`<div id="lifebox" style="display:none"><div id="lifemap"></div><div id="lifelist" class="meta"></div></div><p class="meta">${ps.length} people · ${tot} record stays not yet collated as residence events · ${gp} gaps. Bars: volume years per parish (a move lies where two parishes overlap); thin bars: residence events in the tree; red: years with no volume cited.</p>`+ps.slice(0,150).map(card).join('')+(ps.length>150?`<p class="meta">Showing 150 of ${ps.length}; filter to narrow.</p>`:'')}
function card(P){const ys=[P.born,P.died,...P.record.flatMap(s=>[s.start,s.end]),...P.documented.flatMap(d=>[d.start,d.end])].filter(Boolean).map(Number);
 if(!ys.length){const mb0=(P.path&&P.path.length?` <button class="mapbtn" data-ids="${esc(P.id)}">map</button>${P.spouses.length?` <button class="mapbtn" data-ids="${esc([P.id,...P.spouses].join(','))}">map with spouse</button>`:''}`:'')+geoLink(P);
  return `<div class="vol"><h3>${esc(P.label)} <span class="meta">${esc(P.kin)} ${esc(P.lineage||P.branch||'')} · ${P.path.length} located events, no household examinations cited</span>${mb0}</h3></div>`}
 const y0=Math.min(...ys),y1=Math.max(...ys,y0+1),W=900,x=y=>10+(W-20)*(y-y0)/(y1-y0+1);
 const rec=P.record,doc=P.documented,H=24+16*rec.length+10*doc.length+18;let y=16,bars='';
 rec.forEach(s=>{bars+=`<rect x="${x(s.start)}" y="${y}" width="${Math.max(3,x(s.end+1)-x(s.start))}" height="12" rx="2" fill="${pc(s.parish)}" fill-opacity=".8"><title>${esc(s.parish)} ${esc(s.place)} ${s.start}–${s.end}: ${esc(s.volumes.map(v=>v[0]+' p. '+v[1]).join(', '))}</title></rect><text x="${x(s.end+1)+4}" y="${y+10}">${esc(s.parish)} ${esc(s.place)}</text>`;y+=16});
 doc.forEach(d=>{const a=d.start??y0,b=d.end??y1;bars+=`<rect x="${x(a)}" y="${y}" width="${Math.max(2,x(b+1)-x(a))}" height="5" fill="${pc(d.parish)}" fill-opacity=".45"><title>documented: ${esc(d.date)} ${esc(d.text)}</title></rect>`;y+=10});
 P.gaps.forEach(g=>{bars+=`<rect x="${x(g.start)}" y="10" width="${Math.max(2,x(g.end+1)-x(g.start))}" height="${y-6}" fill="#d33" fill-opacity=".10"/>`});
 [P.born,P.died].forEach((v,i)=>{if(v)bars+=`<line x1="${x(v)}" x2="${x(v)}" y1="8" y2="${y}" stroke="var(--mut)" stroke-dasharray="2 2"/><text x="${x(v)+2}" y="${y+12}">${i?'†':'*'}${v}</text>`});
 bars+=`<text x="10" y="10">${y0}</text><text x="${W-10}" y="10" text-anchor="end">${y1}</text>`;
 const gaps=P.gaps.map(g=>`<li>${g.start}–${g.end}: no volume cited between ${esc(g.after)} and ${esc(g.before)}${g.look.length?'; open '+g.look.map(l=>`<a href="${esc(l.viewer)}" target="_blank" rel="noopener">${esc(l.code)}</a> (${esc(l.years)})`).join(' or '):''}</li>`).join('');
 const moves=P.moves.map(m=>`<li>moved ${esc(m.frm)} → ${esc(m.to)} between ${m.between[0]} and ${m.between[1]}${m.documented.length?' · documented: '+esc(m.documented.join('; ')):''}</li>`).join('');
 const mb=(P.path&&P.path.length?` <button class="mapbtn" data-ids="${esc(P.id)}">map</button>${P.spouses.length?` <button class="mapbtn" data-ids="${esc([P.id,...P.spouses].join(','))}">map with spouse</button>`:''}`:'')+geoLink(P);
 return `<div class="vol"><h3>${esc(P.label)} <span class="meta">${esc(P.kin)} ${esc(P.lineage||P.branch||'')}${P.uncollated?` · <b style="color:var(--FM)">${P.uncollated} not collated</b>`:''}</span>${mb}</h3>
 <svg viewBox="0 0 ${W} ${H}" width="100%">${bars}</svg>${gaps||moves?`<ul class="meta">${moves}${gaps}</ul>`:''}</div>`}
const BYID={};(D.people||[]).forEach(P=>BYID[P.id]=P);
const LKM={farm:.3,village:1,parent:2,parish:6,town:5,region:60,country:300};
const PCOL=['#c0522b','#2f6db5','#2f8f5b','#8a4fb0'];let LMAP=null,LLAY=null;
function geoLink(P){const mhs=[P.mh_id,...(P.spouses||[]).map(s=>(BYID[s]||{}).mh_id)].filter(Boolean);
 return (mhs.length?` <a class="mapbtn" href="geography.html#person=${encodeURIComponent(mhs.join(',')).replace(/%2C/g,',').replace(/%3A/g,':')}&lines=1" target="geography">geography</a>`:'')+(P.record&&P.record.length?` <a class="mapbtn" href="volumes.html#q=${encodeURIComponent(P.label)}" target="volumes">volumes</a>`:'')}
function showMap(ids){const box=document.getElementById('lifebox');if(!box||!window.L)return;box.style.display='';
 if(!LMAP||!document.getElementById('lifemap')._leaflet_id){LMAP=L.map('lifemap');L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:17,attribution:'© OpenStreetMap'}).addTo(LMAP);LLAY=L.layerGroup().addTo(LMAP)}
 LLAY.clearLayers();const all=[];let list='';
 ids.forEach((id,k)=>{const P=BYID[id];if(!P)return;const c=PCOL[k%PCOL.length];
  const pts=P.path;if(!pts.length)return;
  const groups=[];pts.forEach(p=>{const g=groups.find(g=>Math.abs(g.lat-p.lat)<1e-5&&Math.abs(g.lon-p.lon)<1e-5);if(g)g.items.push(p);else groups.push({lat:p.lat,lon:p.lon,level:p.level,items:[p]})});
  let line=pts.filter(p=>p.kind==='documented'&&p.dated).map(p=>[p.lat,p.lon]);
  if(line.length<2)line=pts.filter(p=>p.kind==='documented').map(p=>[p.lat,p.lon]);
  if(line.length>1)L.polyline(line,{color:c,weight:3,opacity:.8}).addTo(LLAY);
  const rec=pts.filter(p=>p.kind==='record').map(p=>[p.lat,p.lon]);
  if(rec.length>1)L.polyline(rec,{color:c,weight:2,opacity:.6,dashArray:'4 6'}).addTo(LLAY);
  groups.forEach(g=>{const n=pts.indexOf(g.items[0])+1;const doc=g.items.some(p=>p.kind==='documented');
   L.circle([g.lat,g.lon],{radius:(LKM[g.level]||5)*1000,color:c,weight:0,fillOpacity:.07}).addTo(LLAY);
   L.circleMarker([g.lat,g.lon],{radius:7,color:c,weight:2,fillColor:doc?c:'#fff',fillOpacity:doc?.9:1})
    .bindTooltip(String(n),{permanent:true,direction:'center',className:'num'})
    .bindPopup(`<b>${esc(P.label)}</b><br>`+g.items.map(p=>`${esc(p.date)} · ${esc(p.event)}: ${esc(p.name)} <i>(${esc(p.level)})</i>`).join('<br>')).addTo(LLAY);
   all.push([g.lat,g.lon])});
  list+=`<p><b style="color:${c}">${esc(P.label)}</b></p><ol>`+pts.map(p=>`<li${p.kind==='record'||!p.dated?' style="opacity:.7"':''}>${esc(p.date)} · ${esc(p.event)} · ${esc(p.name)} <span class="tag">${esc(p.level)}</span>${p.kind==='record'?' <span class="tag">record</span>':''}</li>`).join('')+'</ol>'});
 document.getElementById('lifelist').innerHTML=list+'<p>Line: dated events in the tree (day and month, or birth, marriage, death). Filled marker: an event in the tree; hollow: a household-examination stay; greyed in the list: year-only. Faint circle: how precisely the place is known (farm 0.3 km … parish 6 km).</p>';
 box.scrollIntoView();setTimeout(()=>{LMAP.invalidateSize();if(all.length)LMAP.fitBounds(all,{padding:[30,30],maxZoom:13})},60)}
document.addEventListener('click',e=>{const b=e.target.closest('.mapbtn');if(b)showMap(b.dataset.ids.split(','))});
function go(){if(view==='p'){document.querySelector('aside').style.display='none';document.querySelector('main').style.gridTemplateColumns='1fr';
  document.querySelectorAll('.vonly').forEach(e=>e.style.display='none')}
 view==='v'?render():people();hash()}
function hash(){const h=new URLSearchParams();const q=document.getElementById('q').value,k=document.getElementById('kin').value;
 if(q)h.set('q',q);if(k)h.set('kin',k);if(view==='v'&&cur)h.set('parish',cur);
 history.replaceState(null,'',h.toString()?'#'+h.toString().replace(/%3A/g,':').replace(/%2C/g,','):location.pathname)}
['q','kin','noplac'].forEach(id=>document.getElementById(id).oninput=go);
// link scheme: people.html#q=MH:I800&kin=ancestor  ·  volumes.html#parish=Källeryd&q=Hagelstorp
// (old links volumes.html#view=people&q=… are sent on to people.html)
(function(){const h=new URLSearchParams(location.hash.slice(1));
 if(view==='v'&&h.get('view')==='people'){h.delete('view');location.replace('people.html#'+h.toString());return}
 if(h.get('q'))document.getElementById('q').value=h.get('q');if(h.get('kin'))document.getElementById('kin').value=h.get('kin');
 if(h.get('parish'))cur=h.get('parish')})();
go();
</script></body></html>
"""


# -- command line ----------------------------------------------------------------------

def run(cfg, wikidata=False, gazetteer=None, riksarkivet_lookups=True):
    """The whole pipeline on the configured tree: citations -> volumes ->
    Riksarkivet facts -> gazetteer places -> errata. Returns (rows,
    parishes for display, errata report). Caches are public, in gazetteer/cache/."""
    import config
    import errata
    import gazetteer as gz
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
        r["volume"] = volume_key(r) if r.get("tier") != "plac-only" else ""
        for k in ("notes", "errata"):
            if isinstance(r.get(k), list):
                r[k] = " | ".join(r[k])
    display = {}
    for name, p in gaz.parishes.items():
        display[name] = dict(code=p.get("archive", ""), qid=p.get("wikidata", ""),
                             label=p.get("label", ""), lat=p.get("lat"), lon=p.get("lon"),
                             harad=p.get("harad", ""), status=p.get("archive_from", ""))
    for name, info in parishes.items():
        display.setdefault(name, info)
    return rows, display, report


def _main(argv):
    import config
    import errata
    cfg = config.load()
    rows, parishes, report = run(cfg, wikidata="--wikidata" in argv,
                                 riksarkivet_lookups="--no-riksarkivet" not in argv)
    argv = [a for a in argv if not a.startswith("--")]
    g = cfg.get("gedcom") or {}
    if argv and argv[0] == "farm":
        rx = re.compile(" ".join(argv[1:]), re.I)
        for farm, vols in sorted(farm_index(rows).items()):
            if not rx.search(farm):
                continue
            print(farm)
            for vol, pages in sorted(vols.items()):
                for page, rs in sorted(pages.items(), key=lambda kv: int(kv[0] or 0)):
                    people = sorted({f"{r['label']} [{r['kin']}{' ' + r['branch'] if r['branch'] else ''}]"
                                     for r in rs})
                    print(f"  {vol:32} p.{page or '?':>4}  " + "; ".join(people))
        return
    write_csv(rows, config.path(cfg, "volume_refs.csv"))
    import gazetteer as gz
    import residences
    ra = riksarkivet.Riksarkivet(gz.CACHE / "riksarkivet.json")
    try:
        people = residences.run(rows, ra)
    finally:
        ra.save()
    import geocode
    import gazetteer as gz2
    import lifepath
    private = geocode.Cache(config.path(cfg, "geocode_private.json"))
    tree = gedcom_io.Tree(config.path(cfg, g["file"]), **gedcom_io.options(cfg))
    try:
        paths, unplaced = lifepath.build(rows, people, gz2.load(cfg), private,
                                         network="--geocode" in sys.argv)
    finally:
        private.save()
    n_pts = sum(len(v) for v in paths.values())
    print(f"life paths: {len(paths)} people, {n_pts} located points; "
          f"{sum(len(v) for v in unplaced.values())} events without coordinates or year"
          + ("" if "--geocode" in sys.argv else " (towns abroad: run with --geocode once)"))
    spouse_of = lifepath.spouses(tree)
    for view in ("volumes", "people"):
        write_html(rows, parishes, config.path(cfg, f"{view}.html"), g.get("proband", ""), people,
                   paths, spouse_of, view=view)
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
    print("wrote volume_refs.csv, volumes.html and people.html")


if __name__ == "__main__":
    _main(sys.argv[1:])
