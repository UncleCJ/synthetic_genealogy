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
How it works: docs/records.md, "References and volumes".

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
    import parish_names
    names = parish_names.load() if reference is None else reference

    def part_key(part):
        k = _key(PLAC_SUFFIX.sub("", gazetteer.drop_county_code(part)))
        if k not in plain and k.endswith("s") and k[:-1] in plain:
            k = k[:-1]                                      # "Båraryds kyrka"
        return k

    # Which parish groups of the full list the family's own names stand for
    # ("Norrköpings Östra Eneby" -> the group that "Östra Eneby" also names).
    family_of = {}
    for name in plain.values():
        for g in names.candidates(name):
            family_of.setdefault(g, name)

    def region(p):
        """County, province or country: "Älvsborg", "Alvsborg", "Goteborg Bohus"."""
        return gazetteer.region(p) or gazetteer.region(p.strip() + "s") \
            or bool(parish_names.counties_of(p))

    def lookup(i, parts):
        """(parish name or None, how) for parts[i]: a name the family's
        citations use, else the full parish list, narrowed by the other
        parts (a county, a town). Ambiguous names give None."""
        part = parts[i]
        k = part_key(part)
        if k in plain:
            return plain[k], "family"
        others = parts[:i] + parts[i + 1:]
        counties = [p for p in others if region(p)]
        if not (counties or len(parts) > 1 or PLAC_SUFFIX.search(gazetteer.drop_county_code(part))):
            # a lone name ("Högalid"): more likely the family's own farm
            # (the gazetteer's unique village) than a namesake parish
            return None, "lone name"
        cands = names.candidates(part, counties=counties, towns=others)
        if not cands:
            return None, ""
        fam = {family_of[g] for g in cands if g in family_of}
        if len(fam) == 1:
            return fam.pop(), "parish list, family name"
        if len(cands) == 1:
            return names.label(next(iter(cands))), "parish list"
        want = gazetteer.fold(parish_names.degenitive(parish_names.bare(part)))
        exact = [g for g in cands if gazetteer.fold(names._base_label(g)) == want]
        if len(exact) == 1:
            return names.label(exact[0]), "parish list"
        return None, "ambiguous"

    def explicit(part):
        """A part written as a parish ("Västerlanda förs.") whose name reads
        as a name: capitalised, with no move word left in it."""
        part = gazetteer.drop_county_code(part)
        if not EXPLICIT_PARISH.search(part):
            return ""
        name = degenitive(EXPLICIT_PARISH.sub("", part).strip())      # "Okändhems socken"
        words = [w for w in name.split() if w.lower() != "och"]
        if not words or not all(re.match(r"[A-ZÅÄÖÉ]|S:t", w) for w in words):
            return ""                  # "till Maria", "Byns fattigstuga Torps"
        return name

    def parish_at(parts):
        """(index, name) of the parish among the parts, or (None, None). Rules:
        docs/records.md, "Reading place strings".
        """
        whole = parts
        country = next((i for i, p in enumerate(parts)
                        if p.strip(" .").lower() in gazetteer.COUNTRIES), None)
        if country is not None:
            parts = parts[:country + 1]
        end = len(parts)
        while end > 1 and region(parts[end - 1]):
            end -= 1
        for i in reversed(range(end)):
            if explicit(parts[i]):
                return i, lookup(i, parts)[0] or explicit(parts[i])
        for i in reversed(range(end)):
            name = lookup(i, parts)[0]
            if name:
                # "Haurida, Aneby, Jönköpings län": a modern kommun after a
                # parish, as MyHeritage writes it, or a town ("Västra
                # Vemmenhög, Malmö"); a kommun that is a parish the family's
                # citations name stays ("Åryd, Ödeshög": a village in Ödeshög)
                yields = (names.is_town(parts[i]) or names.is_kommun(parts[i])) \
                    and part_key(parts[i]) not in plain
                if i and yields and lookup(i - 1, parts)[0]:
                    return i - 1, lookup(i - 1, parts)[0]
                return i, name
        for i in range(len(whole)):
            name = lookup(i, whole)[0]
            if name:
                return i, name
        return None, None

    # Parishes written as such ("Kyrkeby, Västerlanda förs., Fuxerna") count
    # for every row, whichever comes first; one the full list knows by
    # another spelling keeps that spelling.
    for r in rows:
        parts = gazetteer.plac_parts(r.get("event_place"))
        for i, part in enumerate(parts):
            name = explicit(part)
            if name and not lookup(i, parts)[0]:
                plain.setdefault(_key(name), name)
    for r in rows:
        parts = gazetteer.plac_parts(r.get("event_place"))
        i, name = parish_at(parts)
        if i is not None:
            k = _key(name)
            # the part next to the parish is usually the village (by);
            # anything before it is a farm or house within it
            r.setdefault("plac_parish", name)
            j = i - 1 if i and _key(parts[i - 1]) in towns.get(k, ()) else i
            farm = gazetteer.drop_county_code(parts[j - 1]) if j else ""   # "Västra Hult (K)"
            if farm and names.is_town(farm):
                farm = ""                 # a town, not a farm ("Göteborg, Göteborgs Karl Johan");
                                          # a farm may share a parish's name ("Ekeby, Storsocken")
            r.setdefault("plac_farm", farm)
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
    import parish_names
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
            "ra_note", "ra_viewer", "ra_images", "ra_nad", "ra_pages", "ra_image_count", "ra_status", "mh_collection",
            "mh_item", "cite_date", "url", "cited_as", "mh_label", "ref_format", "ref_in",
            "aid", "ref_text"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_html(rows, parishes, path, proband_label):
    """The Archives view (archives.html), one self-contained page, private
    (holds names; keep it in data/): parishes with their archive codes on a
    map and in a list, each parish's volumes by series, every volume as a
    page strip with the people cited on each page, and the farms most cited
    across volumes. A chosen parish zooms the map onto its farms and
    villages; a volume's "map" button shows its farms coloured by page, so
    the order the book walks through the parish can be seen. Linked both
    ways with the geography view."""
    keep = ["person", "label", "kin", "branch", "lineage", "event", "event_date",
            "event_place", "tier", "resourced", "parish", "archive_code", "volume",
            "series", "vol", "years", "page", "row", "farm", "plac_detail", "image_id", "image_no",
            "url", "source_title", "mh_volume", "conflict", "ra_code", "code_from", "series_name",
            "place_id", "place", "village", "place_from", "notes", "errata", "mh_id",
            "ra_years", "ra_note", "ra_viewer", "ra_images", "ra_nad", "ra_pages", "ra_image_count", "ra_status", "cited_as", "lat", "lon", "lv"]
    data = [{k: r.get(k, "") or "" for k in keep} for r in rows if r["tier"] != "tree"]
    payload = json.dumps(dict(rows=data, parishes=parishes, proband=proband_label),
                         ensure_ascii=False, default=str)
    import geoview
    page = (HTML.replace("__DATA__", payload.replace("</", "<\\/"))
            .replace("__NAV__", geoview.nav("archives.html")))
    path.write_text(page, encoding="utf-8")


HTML = r"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Archives</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root{--bg:#fbfaf7;--fg:#1d1c1a;--mut:#6b6760;--line:#e2ded6;--card:#fff;--sel:#fff1bf;--acc:#2f6db5;
--FF:#2f6db5;--FM:#c0522b;--MF:#2f8f5b;--MM:#8a4fb0;--anc:#111;--sp:#b9a76a;--un:#b8b4ac}
@media (prefers-color-scheme:dark){:root{--bg:#171614;--fg:#ece9e2;--mut:#9b968c;--line:#34312c;--card:#201f1c;--sel:#4a4220;--acc:#6ea4e6;
--FF:#6ea4e6;--FM:#e8835c;--MF:#5fc38c;--MM:#b98ad8;--anc:#fff;--sp:#9c8d58;--un:#5d5a54}}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.45 system-ui,-apple-system,sans-serif;display:grid;grid-template-columns:300px 1fr;grid-template-rows:auto 1fr}
header{grid-column:1/-1;display:flex;gap:10px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:16px;margin:0 8px 0 0}h2{font-size:15px;margin:14px 0 6px}h3{font-size:13px;margin:0}
h4{font-size:13px;margin:16px 0 4px;color:var(--mut);border-bottom:1px solid var(--line);padding-bottom:2px}
input,select{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 8px}
aside{border-right:1px solid var(--line);padding:8px 10px;overflow:auto;min-height:0;display:flex;flex-direction:column;gap:6px}
#main{padding:8px 18px 24px;overflow:auto;min-height:0}
#map{height:240px;flex:none;border:1px solid var(--line);border-radius:6px}body.inparish #map{height:340px}
#mapnote{font-size:12px;color:var(--mut)}#mapnote .grad{display:inline-block;width:90px;height:8px;border-radius:2px;vertical-align:0;background:linear-gradient(90deg,hsl(220,70%,45%),hsl(120,70%,40%),hsl(20,80%,48%))}
.vol.on{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc)}
#pq{width:100%}
.par{padding:4px 6px;border-radius:4px;cursor:pointer;display:flex;justify-content:space-between;gap:8px}
.par:hover{background:var(--line)}.par.on{background:var(--sel)}
.par small,.meta{color:var(--mut)}.par .n{color:var(--mut);font-variant-numeric:tabular-nums}
.bar{display:flex;height:5px;border-radius:3px;overflow:hidden;margin-top:3px;width:120px}
.t-ra-full{background:#2a7d4f}.t-ra-link{background:#7fbf8f}.t-mh-record{background:#d49a2a}.t-mh-index{background:#e7cf8a}.t-plac-only{background:#bbb}.t-other{background:#ddd}
.legend{display:flex;gap:10px;flex-wrap:wrap;font-size:12px;color:var(--mut)}
.legend span::before{content:"";display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;vertical-align:-1px;background:var(--c)}
.vol{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin:8px 0}
.vol .meta{font-size:12px;margin:2px 0}
.volno{font-family:ui-monospace,Menlo,monospace;background:var(--line);padding:0 4px;border-radius:4px}
svg text{fill:var(--fg);font-size:10px}
a.pay{opacity:.55}
.pages{width:100%;border-collapse:collapse;margin-top:4px}
.pages td{border-top:1px solid var(--line);padding:3px 6px;vertical-align:top}
.pages td:first-child{white-space:nowrap;color:var(--mut);width:70px}
.vol details summary{cursor:pointer;color:var(--mut);font-size:12px}
.who{display:inline-block;margin:0 8px 2px 0}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:0}
.k-ancestor,.k-self{font-weight:600}.k-unlinked{color:var(--mut)}
.tag{font-size:11px;padding:0 5px;border-radius:4px;border:1px solid var(--line);color:var(--mut);margin-left:4px;text-decoration:none}
.tag.note{border-color:var(--FM);color:var(--FM)}
a{color:inherit}a.btn{font-size:12px;font-weight:400;margin-left:6px;padding:1px 8px;border:1px solid var(--line);border-radius:5px;background:var(--card);text-decoration:none}
a.btn:hover{border-color:var(--mut)}
.sum{display:flex;gap:18px;flex-wrap:wrap;margin:6px 0 4px}.sum b{font-size:18px;display:block}
.farms{border-collapse:collapse}.farms td{padding:3px 8px;border-top:1px solid var(--line);vertical-align:top}.farms td.n{color:var(--mut);text-align:right}
@media(max-width:800px){body{grid-template-columns:1fr;grid-template-rows:auto auto 1fr}aside{max-height:45vh;border-right:0;border-bottom:1px solid var(--line)}}
</style></head><body>
<header>__NAV__<h1>Archives</h1>
<input id="q" placeholder="Filter: farm, person, volume…" size="28">
<select id="kin"><option value="">all people</option><option value="family">relatives & ancestors</option><option value="ancestor">ancestors only</option></select>
<label><input type="checkbox" id="noplac" checked> hide uncited places</label>
<div class="legend" id="legend"></div></header>
<aside><div id="map"></div><div id="mapnote"></div>
<input id="pq" placeholder="filter parishes…">
<div class="legend"><span style="--c:#2a7d4f" title="Riksarkivet citation with archive, volume and page">RA full</span><span style="--c:#7fbf8f" title="only a Riksarkivet image link">RA link</span><span style="--c:#d49a2a" title="MyHeritage household-examination record">MH record</span><span style="--c:#e7cf8a" title="other MyHeritage record collections: no volume">MH index</span><span style="--c:#bbb" title="a place with no citation">place only</span></div>
<div id="plist"></div></aside>
<section id="main"></section>
<script>
const D=__DATA__;
const BR={FF:'var(--FF)',FM:'var(--FM)',MF:'var(--MF)',MM:'var(--MM)'};
const TIERS=['ra-full','ra-link','mh-record','mh-index','plac-only','other'];
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const enc=s=>encodeURIComponent(s).replace(/%2C/g,',').replace(/%3A/g,':');
const coll=new Intl.Collator('sv');
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
function color(r){if(r.kin==='self')return 'var(--anc)';if(r.kin==='unlinked')return 'var(--un)';
 if(r.kin==='spouse of relative')return 'var(--sp)';const b=(r.branch||'').split(' ')[0];return BR[b]||'var(--anc)'}
document.getElementById('legend').innerHTML=['FF','FM','MF','MM'].map(k=>`<span style="--c:var(--${k})">${k}</span>`).join('')+'<span style="--c:var(--sp)">spouse of relative</span><span style="--c:var(--un)">unlinked</span>';
// series in the order the books were kept, with plain names where Riksarkivet gives none
const SERIES=['A I','A II a','A II','B','B I','B II','C','C I','E','E I','F','F I'];
const SNAME={'A I':'Household examinations','A II a':'Parish books','A II':'Parish books','B':'Moving in and out','B I':'Moving in','B II':'Moving out',
 'C':'Births and baptisms','C I':'Births and baptisms','E':'Marriages','E I':'Marriages','F':'Deaths and burials','F I':'Deaths and burials'};
let cur=null;
const $=id=>document.getElementById(id);
function filtered(){const q=$('q').value.toLowerCase(),k=$('kin').value,np=$('noplac').checked;
 return D.rows.filter(r=>(!np||r.tier!=='plac-only')&&(!k||(k==='ancestor'?['ancestor','self'].includes(r.kin):['ancestor','self','relative'].includes(r.kin)))
  &&(!q||[r.farm,r.place,r.label,r.volume,r.event_place,r.parish,r.notes,r.ra_code].join(' ').toLowerCase().includes(q)))}
function byParish(rows){const by={};rows.forEach(r=>{if(r.parish)(by[r.parish]=by[r.parish]||[]).push(r)});return by}
function plist(by){const pq=$('pq').value.toLowerCase();
 const names=Object.keys(by).filter(n=>!pq||n.toLowerCase().includes(pq)||n===cur).sort((a,b)=>by[b].length-by[a].length||coll.compare(a,b));
 $('plist').innerHTML=names.map(n=>{const c={};by[n].forEach(r=>c[r.tier]=(c[r.tier]||0)+1);const tot=by[n].length;const p=D.parishes[n]||{};
  return `<div class="par ${n===cur?'on':''}" data-p="${esc(n)}"><div><b>${esc(n)}</b> <small>${esc(p.code||'')}</small>
  <div class="bar">${TIERS.filter(t=>c[t]).map(t=>`<div class="t-${t}" style="width:${100*c[t]/tot}%" title="${t}: ${c[t]}"></div>`).join('')}</div></div><span class="n">${tot}</span></div>`}).join('')||'<p class="meta">No parish matches.</p>'}
$('plist').addEventListener('click',e=>{const p=e.target.closest('.par');if(p)pick(p.dataset.p===cur?null:p.dataset.p)});
// map: one circle per parish, sized by its citations
const map=L.map('map',{zoomControl:false,attributionControl:false});
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:15}).addTo(map);
const dots=L.layerGroup().addTo(map);let FITKEY='',VOL=null;
// page position in a volume as a colour: first page blue, last red
const pageCol=f=>`hsl(${220-200*f},70%,${45-5*Math.sin(Math.PI*f)}%)`;
function drawMap(by){dots.clearLayers();const pts=[];const acc=css('--acc')||'#2f6db5';document.body.classList.toggle('inparish',!!cur);
 Object.entries(by).forEach(([n,rs])=>{const p=D.parishes[n];if(!p||p.lat==null)return;if(!cur)pts.push([p.lat,p.lon]);
  L.circleMarker([p.lat,p.lon],{radius:cur?(n===cur?6:3):3+Math.sqrt(rs.length)/1.5,weight:n===cur?2.5:1,color:n===cur?'#d49a2a':'#fff',fillColor:n===cur?'#d49a2a':acc,fillOpacity:cur&&n!==cur?.35:.75})
   .bindTooltip(`${esc(n)} · ${rs.length}`).on('click',()=>pick(n===cur?null:n)).addTo(dots)});
 let note='';
 if(cur){// the chosen parish's farms and villages; with a volume chosen, only its own, coloured by page
  const rs=(by[cur]||[]).filter(r=>!VOL||r.volume===VOL);const F={};let centre=0;
  rs.forEach(r=>{if(r.lat===''||r.lat==null){centre++;return}const k=r.place_id;(F[k]=F[k]||[]).push(r)});
  const mx=VOL?Math.max(1,...rs.map(r=>+r.page||0)):0;
  Object.values(F).sort((a,b)=>b.length-a.length).forEach(fr=>{const r0=fr[0];const pg=fr.map(r=>+r.page).filter(x=>x>0);
   const lo=pg.length?Math.min(...pg):null,hi=pg.length?Math.max(...pg):null;
   const fill=VOL?(lo!=null?pageCol(((lo+hi)/2)/mx):'#999'):acc;pts.push([r0.lat,r0.lon]);
   const vols=[...new Set(fr.map(r=>r.volume).filter(Boolean))];
   L.circleMarker([r0.lat,r0.lon],{radius:4+Math.sqrt(fr.length),weight:1,color:'#fff',fillColor:fill,fillOpacity:.9})
    .bindTooltip(`<b>${esc(r0.place||r0.farm)}</b> <span style="opacity:.7">(${esc(r0.lv)})</span><br>${fr.length} citation${fr.length===1?'':'s'}`+
     (VOL?(lo!=null?`, ${lo===hi?'p. '+lo:'pp. '+lo+'–'+hi}`:''):(vols.length?`<br>${vols.length} volume${vols.length===1?'':'s'}`:'')))
    .on('click',()=>{$('q').value=r0.place||r0.farm;VOL=null;go()}).addTo(dots)});
  if(!pts.length){const p=D.parishes[cur];if(p&&p.lat!=null)pts.push([p.lat,p.lon])}
  note=(VOL?`<b>${esc(VOL)}</b>: page <span class="grad"></span> first → last · <a href="#" id="novol">all volumes</a>`:`Farms and villages of ${esc(cur)}, sized by citations; click one to filter`)+
   (centre?`<br>${centre} without a point of their own (at the parish only)`:'')}
 $('mapnote').innerHTML=note;const nv=$('novol');if(nv)nv.onclick=e=>{e.preventDefault();VOL=null;go()};
 const key=cur+'|'+VOL+'|'+pts.map(String).join(';');
 if(key!==FITKEY&&pts.length){FITKEY=key;map.invalidateSize();map.fitBounds(pts,{padding:[18,18],maxZoom:cur?13:10})}}
function who(r){return `<span class="who k-${r.kin.replace(/ /g,'-')}" title="${esc(r.kin)} ${esc(r.lineage||r.branch)} · ${esc(r.event)} ${esc(r.event_date)} · ${esc(r.tier)}${r.resourced?' (re-sourced)':''}"><span class="dot" style="background:${color(r)}"></span>${esc(r.label)}${r.row?` <span class="tag">rad ${esc(r.row)}</span>`:''}${imglink(r)}${r.url?` <a class="${/riksarkivet\.se/.test(r.url)?'':'pay'}" href="${esc(r.url)}" target="_blank" rel="noopener" title="${/riksarkivet\.se/.test(r.url)?'Riksarkivet':/myheritage/i.test(r.url)?'MyHeritage (subscription)':/arkivdigital/i.test(r.url)?'Arkiv Digital (subscription)':'the citation\'s link'}">↗</a>`:''}${r.notes?` <span class="tag note" title="${esc(r.notes)}">note</span>`:''}${r.errata?` <span class="tag note" title="${esc(r.errata)}">corrected</span>`:''}</span>`}
const BILD=(id,n)=>`https://sok.riksarkivet.se/bildvisning/${id}_${String(n).padStart(5,'0')}`;
function span(r){const m=/^(\d+)-(\d+)(?: (\w+))?/.exec(r.ra_pages||'');return m?{a:+m[1],b:+m[2],unit:m[3]||'page'}:null}
// the image a page is likely on, from its place in the page span: a guess, shown with ≈
function guess(r){const s=span(r),n=+r.ra_image_count,p=+r.page;if(!s||!n||!r.ra_images||!(p>=s.a&&p<=s.b))return 0;
 return Math.min(n,Math.max(1,Math.round(1+(n-1)*(p-s.a)/Math.max(1,s.b-s.a))))}
function imglink(r){if(r.image_id&&r.image_no)return ` <a class="tag" href="${BILD(esc(r.image_id),r.image_no)}" target="_blank" rel="noopener">bild ${esc(r.image_no)}</a>`;
 const g=guess(r);return g?` <a class="tag" href="${BILD(esc(r.ra_images),g)}" target="_blank" rel="noopener" title="estimated from the page's place in the volume (${esc(r.ra_pages)}, ${esc(r.ra_image_count)} images): look a few images either side">≈ bild ${g}</a>`:''}
// the page strip runs over the volume's page span where Riksarkivet's note gives
// it, else to the highest cited page (or the image count, when larger): an estimate
function strip(rows){const pg=rows.map(r=>+r.page).filter(x=>x>0);if(!pg.length)return '';const hi=Math.max(...pg),W=900,H=46;
 const ra=rows.find(r=>r.ra_status==='found')||{},s=span(ra),n=+ra.ra_image_count||0;
 const lo=s&&s.a<=Math.min(...pg)?s.a:1,mx=s&&s.b>=hi?s.b:Math.max(hi,n);
 const end=s&&s.b>=hi?`${mx}${s.unit==='page'?'':' ('+s.unit+')'}`:n>hi?`~${n} images`:`≥ ${hi} (highest cited)`;
 const farms={};rows.forEach(r=>{const fn=r.place||r.farm;if(+r.page>0&&fn){const f=farms[fn]=farms[fn]||[1e9,0];f[0]=Math.min(f[0],+r.page);f[1]=Math.max(f[1],+r.page)}});
 const x=p=>8+(W-16)*(p-lo)/Math.max(1,mx-lo);
 return `<svg viewBox="0 0 ${W} ${H+14*Object.keys(farms).length}" width="100%"><line x1="8" x2="${W-8}" y1="20" y2="20" stroke="var(--line)" stroke-width="6"/>
 ${rows.filter(r=>+r.page>0).map(r=>`<line x1="${x(+r.page)}" x2="${x(+r.page)}" y1="10" y2="30" stroke="${color(r)}" stroke-width="2"><title>p. ${esc(r.page)}: ${esc(r.label)} (${esc(r.place||r.farm)})</title></line>`).join('')}
 <text x="8" y="44">${lo}</text><text x="${W-8}" y="44" text-anchor="end">${esc(end)}</text>
 ${Object.entries(farms).sort((a,b)=>a[1][0]-b[1][0]).map(([f,[a,b]],i)=>`<rect x="${x(a)-2}" y="${50+14*i}" width="${Math.max(4,x(b)-x(a)+4)}" height="9" rx="2" fill="#7a8fa8" fill-opacity=".45"/><text x="${x(b)+6}" y="${58+14*i}">${esc(f)} ${a===b?'p. '+a:'pp. '+a+'–'+b}</text>`).join('')}</svg>`}
function volhead(v,rs,yrs){const r=rs.find(x=>x.ra_code)||rs[0];
 if(!r.series||v.startsWith('—'))return `<h3>${esc(v)}</h3>`;
 const ra=rs.find(x=>x.ra_status==='found');const ry=ra?ra.ra_years:'';
 const mhy=[...new Set(rs.filter(x=>x.tier==='mh-record'&&x.years).map(x=>x.years.replace('-','–')))];
 const conf=[...new Set(rs.map(x=>x.conflict).filter(Boolean))];const vn=[...new Set(rs.map(x=>x.notes).filter(Boolean))];
 return `<h3><span class="volno">${esc(r.series)}/${esc(r.vol)}</span> · ${esc(ry||yrs.replace('-','–'))}${cur?`<a class="btn" href="#" data-vol="${esc(v)}" title="Its farms on the map beside, coloured by page">map</a>`:''}<a class="btn" href="geography.html#q=${enc(v)}&layer=record&kin=all" target="geography">geography</a></h3>
 <div class="meta">${r.ra_code?(ra&&ra.ra_viewer?`<a href="${esc(ra.ra_viewer)}" target="_blank" rel="noopener">${esc(r.ra_code)}</a> (opens the volume at Riksarkivet; code from ${esc(r.code_from)})`:esc(r.ra_code)+' · '+esc(r.ra_status||'not looked up'))+(ra&&ra.ra_nad?` · <a href="${esc(ra.ra_nad)}" target="_blank" rel="noopener" title="the volume's page in Riksarkivet's catalogue (NAD)">catalogue</a>`:'')+(ra&&(ra.ra_pages||ra.ra_image_count)?` · ${ra.ra_pages?(span(ra).unit==='page'?'pp. ':span(ra).unit+' ')+esc(ra.ra_pages.split(' ')[0].replace('-','–')):''}${ra.ra_pages&&ra.ra_image_count?', ':''}${ra.ra_image_count?esc(ra.ra_image_count)+' images':''}`:''):'archive code unknown: no tidied citation or unique Wikidata match for this parish'}
 ${ra&&ra.ra_note?`<br>Riksarkivet note: <i>${esc(ra.ra_note)}</i>`:''}
 ${mhy.length&&ry&&mhy.some(y=>y!==ry)?`<br>MyHeritage label years: ${esc(mhy.join(', '))}`:''}
 ${conf.length?`<br><b style="color:var(--FM)">Check: ${esc(conf.join('; '))}</b>`:''}${vn.length?`<br>Notes: ${esc(vn.join(' | '))}`:''}</div>`}
function volume(v,rs){const pages={};rs.forEach(r=>{const k=r.page||'';(pages[k]=pages[k]||[]).push(r)});
 const keys=Object.keys(pages).sort((a,b)=>(+a||1e9)-(+b||1e9));const yrs=(rs.find(r=>r.years)||{}).years||'';
 const fam=rs.filter(r=>['ancestor','relative','self'].includes(r.kin)).length;const people=new Set(rs.map(r=>r.person)).size;
 const table=`<table class="pages">${keys.map(k=>{const fs=[...new Set(pages[k].map(r=>r.place&&r.place!==r.farm?r.place+(r.farm?' ('+r.farm+')':''):r.farm).filter(Boolean))];const seen=new Set();
  return `<tr><td>${k?'p. '+esc(k):(pages[k][0].image_no?'img '+esc(pages[k][0].image_no):'')}</td><td>${fs.length?`<b>${esc(fs.join(' / '))}</b><br>`:''}${pages[k].filter(r=>{const s=r.person+r.event;if(seen.has(s))return false;seen.add(s);return true}).map(who).join('')}</td></tr>`}).join('')}</table>`;
 const open=keys.length<=12||$('q').value;
 return `<div class="vol${v===VOL?' on':''}">${volhead(v,rs,yrs)}<div class="meta">${rs.length} citation${rs.length===1?'':'s'} of ${people} ${people===1?'person':'people'}, ${fam} of the family</div>${strip(rs)}
 <details ${open?'open':''}><summary>${keys.length} page${keys.length===1?'':'s'}</summary>${table}</details></div>`}
function render(){const rows=filtered(),by=byParish(rows);plist(by);drawMap(by);const M=$('main');
 if(!cur&&!$('q').value){M.innerHTML=overview(rows,by);return}
 const sel=rows.filter(r=>!cur||r.parish===cur);
 const vols={};sel.forEach(r=>{const v=r.volume||(r.tier==='plac-only'?'— places without a citation':'— records without a volume');(vols[v]=vols[v]||[]).push(r)});
 const yr=v=>+((vols[v].find(r=>r.years)||{}).years||'9999').slice(0,4);
 const ser=v=>{const s=(vols[v][0]||{}).series||'';const i=SERIES.indexOf(s);return v.startsWith('—')?999:i<0?500:i};
 const order=Object.keys(vols).sort((a,b)=>ser(a)-ser(b)||coll.compare(vols[a][0].parish||'',vols[b][0].parish||'')||yr(a)-yr(b)||coll.compare(a,b));
 const p=D.parishes[cur]||{};let h='',last=null;
 if(cur)h+=`<h2>${esc(cur)}<a class="btn" href="geography.html#parish=${enc(cur)}&kin=all" target="geography">geography</a> <small class="meta" style="font-weight:400">${esc(p.code||'')} ${p.qid?`<a href="https://www.wikidata.org/wiki/${p.qid}" target="_blank" rel="noopener">${p.qid}</a> ${esc(p.label)}`:''} ${esc(p.harad||'')} ${p.status?'· '+esc(p.status):''}</small></h2>`;
 else h+=`<h2>Filtered: “${esc($('q').value)}”</h2>`;
 h+=`<p class="meta">${Object.keys(vols).filter(v=>!v.startsWith('—')).length} volumes, ${sel.length} citations.</p>`;
 order.forEach(v=>{const rs=vols[v];const s=v.startsWith('—')?'—':(rs[0].series||'');const g=cur?s:s+'|'+rs[0].parish;
  if(g!==last){last=g;h+=v.startsWith('—')?'<h4>Without a volume</h4>':`<h4>${cur?'':esc(rs[0].parish)+' · '}${esc(s)} · ${esc(rs[0].series_name||SNAME[s]||'')}</h4>`}
  h+=volume(v,rs)});
 M.innerHTML=h}
function overview(rows,by){const vols=new Set(rows.filter(r=>r.volume).map(r=>r.volume));const t={};rows.forEach(r=>t[r.tier]=(t[r.tier]||0)+1);
 const coded=Object.keys(by).filter(n=>(D.parishes[n]||{}).code).length;
 return `<div class="sum"><div><b>${Object.keys(by).length}</b>parishes (${coded} with an archive code)</div><div><b>${vols.size}</b>volumes cited</div><div><b>${rows.length}</b>citations and places</div>
 <div><b>${t['ra-full']||0}</b>tidy Riksarkivet citations</div></div>
 <p class="meta">Pick a parish on the map or in the list for its volumes by series, page by page. Filter by a farm, a person or a volume to see it across every parish.</p>`+farmsAll(rows)}
function farmsAll(rows){const F={};rows.forEach(r=>{const fn=r.place||r.farm;if(!fn||!r.parish||r.cited_as)return;const k=fn+'\u0000'+r.parish;(F[k]=F[k]||[]).push(r)});
 const ks=Object.keys(F).sort((a,b)=>F[b].length-F[a].length).slice(0,80);
 return `<h2>Farms and villages, most cited first</h2><table class="farms">${ks.map(k=>{const [fn,par]=k.split('\u0000');const vs={};F[k].forEach(r=>{const v=r.volume||'(no volume)';(vs[v]=vs[v]||new Set()).add(r.page)});
 const yr=v=>+((F[k].find(r=>(r.volume||'(no volume)')===v&&r.years)||{}).years||'9999').slice(0,4);
 return `<tr><td><b>${esc(fn)}</b>, <a href="#parish=${enc(par)}" data-p="${esc(par)}">${esc(par)}</a></td><td class="n">${F[k].length}</td><td>${Object.entries(vs).sort((a,b)=>yr(a[0])-yr(b[0])).map(([v,s])=>esc(v)+(([...s].filter(Boolean).length)?' p. '+[...s].filter(Boolean).sort((a,b)=>a-b).join(', '):'')).join('<br>')}</td></tr>`}).join('')}</table>`}
$('main').addEventListener('click',e=>{const a=e.target.closest('a[data-p]');if(a){e.preventDefault();pick(a.dataset.p);return}
 const b=e.target.closest('a[data-vol]');if(b){e.preventDefault();VOL=VOL===b.dataset.vol?null:b.dataset.vol;const y=$('main').scrollTop;go();$('main').scrollTop=y}});
function pick(p){cur=p;VOL=null;go();$('main').scrollTop=0}
function go(){render();hash()}
function hash(){const h=new URLSearchParams();const q=$('q').value,k=$('kin').value;
 if(cur)h.set('parish',cur);if(q)h.set('q',q);h.set('kin',k||'all');if(!$('noplac').checked)h.set('uncited','1');
 history.replaceState(null,'','#'+h.toString().replace(/%3A/g,':').replace(/%2C/g,','))}
['q','kin','noplac'].forEach(id=>$(id).oninput=go);$('pq').oninput=()=>plist(byParish(filtered()));
// link scheme: archives.html#parish=Källeryd&q=Hagelstorp&kin=all (uncited=1 shows places without a citation)
// (an address with no filter opens on the ancestors; kin=all for everyone)
function readHash(){const h=new URLSearchParams(location.hash.slice(1));$('q').value=h.get('q')||'';
 const k=h.get('kin');$('kin').value=k?(k==='all'?'':k):(h.get('q')||h.get('parish')?'':'ancestor');cur=h.get('parish')||null;$('noplac').checked=h.get('uncited')!=='1'}
window.addEventListener('hashchange',()=>{readHash();render()});
readHash();go();setTimeout(()=>{map.invalidateSize();FITKEY='';render()},0);
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
        c = gaz.coords(r["place_id"]) if r.get("place_id") else None
        if c and c[2] != "parish":             # a point of its own (farm, village, ...)
            r["lat"], r["lon"], r["lv"] = round(c[0], 5), round(c[1], 5), c[2]
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
    write_html(rows, parishes, config.path(cfg, "archives.html"), g.get("proband", ""))
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
