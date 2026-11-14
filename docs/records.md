# How the records work

The ideas and the reasoning behind the records: places, archive
references, residences and corrections. Terms: [concepts.md](concepts.md).
Modules: [architecture.md](architecture.md). The tools and their commands:
[pipeline.md](pipeline.md#records-tools-run-by-hand). The public gazetteer's
files: [gazetteer/README.md](../gazetteer/README.md).

## Parishes, congregations and towns

*Adopted 2026-11-10, not implemented yet* (decision in concepts.md; work
order in the roadmap, places).

The bare string `parish` does five jobs: the old territory (socken), the
congregation that kept the books (församling), the archive (kyrkoarkiv),
sometimes the town, and the namespace for place ids. Mostly these
coincide; where they don't, folding them loses information.

Gränna shows it. The socken was split in 1652 into a stadsförsamling and a
landsförsamling, rejoined in 1963 as a new Gränna församling. Both kept
their books in one archive (SE/VALA/00106), which made folding look
harmless, but Riksarkivet's volume notes keep them apart: A I volumes from
about 1851 to 1899 are marked "Landsförsamlingen" or "Stadsförsamlingen",
A II a volumes "Landsbygden" or "Staden"; earlier volumes are combined. A
record's parish column may say just "Gränna" for either.

The parish keys today follow no single rule: bare names, names with a
lands-/stads- suffix, city-prefixed urban parishes, combined pastorates
beside their parts, a key with a date in it, a county qualifier, and town
names that hide whether they mean the town or the congregation. Code folds
too: parish lookup strips lands-/stads- suffixes, archive names are
de-genitived by spelling, and residences and stays compare parish strings
for equality.

**How Wikidata models a parish over time.** A socken (Q1523821) carries
its civil-parish code (P777) and a härad (P131); in 1863 it is "replaced
by" (P1366, qualified by P518) a landskommun and a församling. A
församling (Q615980) carries the archive code (P5324) and parish codes
(P778) with validity dates, changing with the 1952, 1967/71, 1974 and 1998
reforms (the first two digits are the county), and a dissolution date
(P576) when merged. From 2016 a distrikt (Q18333556) is the registration
unit. P14316 also carries TORA farm ids, but on about 50 items only. The
query service is often rate-limited, so `places.py` uses the action API's
`haswbstatement` search.

**What the sources already model.** Wikidata has separate items per era,
and names are not identities (two of Gränna's items share a name). Archive
codes follow the lineage, not the congregation: volumes from the socken era
sit in an archive named after today's parish, so an archive code returns a
list of items (`places.py` expects that). Församling items carry dated
parish codes, inception, dissolution and successions. Skatteverket's
"Sveriges församlingar genom tiderna" gives dated names, splits, mergers
and pastorates per congregation, including the non-territorial ones
(regiments, admiralty, castles, hospitals) where Wikidata is thin.

**The model.** Anchor on what can be identified exactly, derive the rest:

- **Archive** (Riksarkivet reference code): exact from a citation.
- **Volume** (archive + series/volume): exact from a citation; its note can
  say which congregation it covers. An untagged volume covers every
  congregation of that archive alive at its date.
- **Congregation** (the Wikidata item of that era): the gazetteer's parish
  entity, the unit the books were kept by. Derived from archive, date and
  volume tag, or from a written name as a candidate.
- **Socken** (Wikidata item): the territory, for geography and the time
  before 1863.
- **Town** (stad, köping): a place of its own kind with its own point,
  linked to its stadsförsamling.

When nothing decides between congregations, the archive is the honest
answer: "Gränna" with a combined volume stays at the archive, narrowed by
date, then volume tag, then the farm's known congregation (the same
candidates idea as for ambiguous names like "Ryr"). Downstream, an archive
and one of its congregations are compatible, not a move.

**Conventions.** Every congregation carries its Wikidata item. Its key is
the Wikidata label without the generic "församling", keeping what tells two
apart ("Gränna stadsförsamling"); a period only on a name clash ("Gränna
(–1652)"). Old keys become aliases, so place ids, the place map, errata and
the store keep resolving. Farms belong to the congregation they were
registered in; the socken is their geographic parent.

**Caveats.** Wikidata's modelling was read through Swedish Wikipedia's
infoboxes; Gränna landsförsamling's own item is not confirmed. Volume-note
wording varies by archive, so tagging needs a small hand-kept pattern list
and will miss some. Pre-1851 Gränna rows can be narrowed only by farm, and
many will rightly stay at the archive.

## Reading place strings

MyHeritage stays the master for people and events. Its place strings are
never edited; they are *resolved* to gazetteer entries on every run, so a
fresh export gives the same output and anything new shows up as a to-do.

**Evidence, strongest first** (`places.py`): a Riksarkivet citation's
reference code (SE/VALA/00472, on the församling's Wikidata item, so the
match is exact); a vendor's volume label ("Bok: Lane-Ryr AI7, 1861 -
1867": the parish and volume, by name only); a free-text place, which only
gives candidates (four parishes are called "…-Ryr"), chosen by date and
the family's known residences.

**Before matching** (`textfix.py`): vendor exports damage Swedish letters
four ways, and an undamaged and a damaged "Gränna" would split one parish
in two: decomposed letters (NFC fixes them), spacing marks turned into
characters ("Ka¨lleryd", re-attached), mojibake ("SkÃ¶vde", re-decoded
exactly as UTF-8) and HTML entities, sometimes encoded twice. The repair is
narrow: ¨ joins only a, o, u, since it also serves as a quote mark.

**A whole place string** ("Torpet Ödelyckan, Adelöf, Adelöv, Jönköpings
län, Sverige") is split into parts (`plac_parts`; "till X" read as its
destination X) and resolved by `Gazetteer.explain_plac`, which the store,
the map and `places_rules.py` share, so the rule a page names is the rule
that fired. The order:

1. the private `plac_map.toml` overrides;
2. a string outside Sweden stops here, unresolved, for the store to
   geocode (below);
3. the first part that is a known parish, with the parts before it tried
   as a place (neighbouring parts joined first, "Finnanäs, Norrgård" →
   Finnanäs Norrgård, then each part, most specific first);
4. a village name unique to one parish, only when nothing but a county,
   province, country, kommun, another place of that parish or the parish's
   own name misspelt follows it: in "Storegården, Fuxerna, Älvsborgs" the
   unknown "Fuxerna" may be the parish, so a Storgården elsewhere is no
   answer;
5. the full parish list (`parish_names.py`, every socken and församling on
   Wikidata) when no part is a gazetteer parish;
6. last resorts: regions written short ("Älvsb. l.", "Jnkpng", "AB-län"),
   county letters as a written county, parish kinds abbreviated (sn, fs,
   Stadsf.), "St." as Stora or Sankt, names in brackets, and, only after
   the farms and on a unique hit, a lone parish name, old spelling (Jerfsö,
   Adelöf), lost å/ä/ö and short forms, dotted or before the parish's kind
   (Sexdr., "Masth Fs"). A lone kommun's name is its town, left to
   geocoding, as is an institution in a town ("Lunds Lasarett").
   Two letters with a dot name a county when only one county or province
   begins with them ("Fuxerna Äl."; "St." names none).

Swedish postcodes are dropped, splitting a street from its post town
("Eriksfältsg 71B 214 55 Malmö" → Eriksfältsg 71B, Malmö), and a street is
written out in labels where there is no doubt (`gazetteer.street`:
Eriksfältsgatan 71 B; a name ending in a street's kind, or cut to g or v
with a house number after it; "Berg 12" may be a farm and is left alone).

The parish among the parts (`volumes.parish_at`): a part written as a
parish ("Västerlanda förs.") wins; otherwise the rightmost parish once
county, province and country are dropped, since a farm to its left can
share a parish's name ("Åryd, Ödeshög"). Two places run together are read
up to the first country. A modern kommun named like a parish, right after a
parish ("Båraryd, Gislaved"), gives way to it; a town's name alone
("Ystad") names no parish.

**The parish list** indexes every form a parish is written in, folded: the
label without its kind and genitive ("Barkeryds socken" → Barkeryd; also
stads-, lands-, domkyrkoförsamling), the aliases, a town's congregation
without its town ("Norrköpings Östra Eneby" → Östra Eneby, the town kept so
a string naming it can prefer it), abbreviations ("Ö. Eneby", "St. Malm").
A name gives candidate *parish groups*: a socken and the församlingar it
became, since "X socken" and a volume of "X församling" are one parish to
the records. A county written in the same string narrows them, mapped from
historical to today's counties; Wikidata's P131 has no dates, so a parish
that moved county is narrowed wrongly. The genitive rule also indexes
"Fors" as "For". On two families the list gave 585 and 426 more place rows
a parish (none lost), and unresolved events fell from 1,269 to 866 and from
909 to 370 with the last resorts; the rest are mostly abroad, towns alone
or a county only.

**Places abroad** (`gazetteer.country`, one country list): a string
whose last part is a country, a US state, a Norwegian fylke, or Danish or
Norwegian words or letters, skips the Swedish rules; the store geocodes it,
at the country itself when nothing finer is found, and labels keep it as
written (the hierarchy adds the country when only a state or such words
say it). On two families unresolved events fell from 258 to 191 and from
208 to 187.

**The gazetteer's entries** (`gazetteer.py build`) come only from places of
record: household-examination citations and parts of place strings before
1950 without digits or street words, so modern addresses stay out of the
public file. Variants match after `fold()` (case, w/v, q/k, ph/f, th/t,
dt/t, gd = gård, doubled letters); anything looser (Kjellerö ~ Källerö) is
proposed for a person to accept. A written name is reduced to one: of "A
eller B" the last; a parish in front dropped; a known village or rote in
front of a farm becomes `within` ("Roten Ingarp Rote Swenshult" → the farm
Svenshult within Ingarps rote). Each entry is named in its least
redundant, modern spelling, every written form kept as a variant. Each
build re-applies the rules to unchecked entries, so a new rule cleans up
what earlier runs added. Ids are "Parish/Name"; rename by adding the old
name as a variant.

**Whole hierarchies** (`place_hierarchy.py`). A tree writes one place many
ways ("Dädesjö, Uppvidinge"; "Uppvidinge, Kronobergs län"; "Adelöv (F),
Småland"). Each string is read into levels (detail, parish, town or
kommun, landskap, län, country), and missing levels are filled from the
tree's other strings: each string naming a level votes for the broader
levels beside it, filled at two thirds agreement; a county letter names
its län; the parish list gives a unique parish's län; a län within one
landskap gives it. What is written is never replaced. On one family, map
points with no level above the farm fell from 8,925 to 1,219 of 16,179.
Unvalidated: a misreading repeated often enough wins.

**Coordinates** (`geocode.py`) carry their level and source: farm (TORA,
OpenStreetMap; ~0.3 km), village (~1 km), parent (a croft without its own
point, ~2 km), parish (Wikidata, ~6 km), town (~5 km), region. A candidate
must lie near its parish, since same-named farms are common. Nominatim is
asked once a second, identified, cached, inside a box around the parish;
street names and numbers are never sent.


## References and volumes

Household-examination books are ordered by village and farm, so a farm
occupies a page range in each volume. Seen per volume, the cited pages show
where the family's farms sit in the book, which neighbouring pages hold
relatives, and which are cited only for in-laws or people not linked to us.

**One reference reader** (`references.py`) reads a volume reference however
it was written: Riksarkivet's citation (with the archive's name, or led by
the code), Arkiv Digital's ("Byn (F) AI:9 (1836-1840) Bild 56 / sid 112"),
a MyHeritage household-examination label (double-letter series, one-year
volumes), or a Riksarkivet image alone. Series are written as Riksarkivet
writes them ("AIIa" → "A II a"). A span is read once: a Riksarkivet
citation wins over an Arkiv Digital reading of it, and an image link right
after a volume reference joins it. Arkiv Digital's "Bild" is its own image
number, never Riksarkivet's. References are read in source citations and
in notes, addresses and event values; a reference in an address is not
read as a place.

**The archive schema.** Swedish parish archives share one layout, the
general archive schema (*allmänna arkivschemat*): the series letter says
what a volume holds, the same in every parish. A household examinations
and parish registers, B moving in and out, C births and baptisms, D
confirmations, E banns and marriages, F deaths and burials, then the
accounts and the rest. A reference code (`A II a/3`) is series, roman
subseries, letter subseries and volume; its order is numeric, not
alphabetical (IX after V, `a/10` after `a/9`). `references.series` reads
roman numerals up to IV.

**What a citation supports.** MyHeritage attaches its record matches,
household-examination citations and other trees' citations to the person
as a whole; only a few dozen citations hang on one event (a residence, a
birth). So a reference supports the person, rarely a claim, and which
claim it bears on is left to the reader (the volume's span against the
person's events).

**Tidiness tiers** (`volumes.py`): ra-full (a Riksarkivet citation, or an
Arkiv Digital one naming the volume as fully), ra-link (an image link
alone, its volume found through other citations of the same image series,
or through a volume of the event's parish and series listing that series
at Riksarkivet: 90 of 127 such rows on one family), mh-record (a MyHeritage
household-examination match), mh-index (other collections: a record but no
volume), tree, plac-only. Volumes are keyed (parish, series, volume):
"AIIa2" and "A II a/2" are one book. MyHeritage's page and row are its
indexers' reading; Riksarkivet's "sida" is the book's page, not the image.
Each cited person is classed against the proband: ancestor, relative by
branch, spouse of a relative, unlinked.

**Riksarkivet's facts** (`riksarkivet.py`, open OAI-PMH, no key). A
reference code is the archive (SE/VALA/00472) plus series and volume; its
record gives the year range, a content note (often the part of the parish
or the page span, "I. 1 - 250. Södra delen."), the image series (so a
citation's bildid prefix should equal it, else citation and volume
disagree), the catalogue (NAD) page and a IIIF manifest counting the
images. An archive's own record is its whole inventory, so one request
serves every volume, and codes damaged in copying (spaces lost, l for 1)
are matched against it. On one family: page spans for 185 of 744 cited
volumes, image counts for 364 (series starting with C have no open
manifest), 78 damaged codes resolved. Citations link the cited image, else
a guessed image for the page (≈), else the volume, in place of paywalled
links. Wikidata's catalogue link works only in a browser (scripts get a
captcha): a link for people, never a lookup.


## Residences and stays

MyHeritage records presence per volume, not when a person moved: every
household-examination match becomes "Residence: <farm>, BET <first year of
the volume> AND <last>". **Stays** (`stays.py`, a derived view) aggregate
them: entries at one place whose years overlap or touch become one stay;
day-dated entries (collated by hand) keep their dates and absorb year-only
ones; stays at different places with exactly one volume's span form a
period group (moved within the period, or served in another household); a
stay known only as a rote, parish or town folds into overlapping farm
stays in the same parish that cover at least half its years. "Same place"
is the gazetteer place, else the text as written. Moves inside a volume
period are not ordered; the records do not say.

**Residence histories** (`residences.py`) set the volume citations, as
record stays merged across consecutive volumes, against the tree's own
residence events, and report per person the gap years with no volume cited
(with the next volume to open, looked up at Riksarkivet), moves between
parishes bracketed by volume years, and record stays not yet collated. A
stay's years are its volume's years, so moves are only bracketed.


## Errata

Corrections and notes live beside the master export, never in it
(principle 1 in concepts.md). Each entry is keyed by something that
survives re-exports (a MyHeritage record, a Riksarkivet image, a volume, a
person, a gazetteer place, a raw place string), records what the export
said (`was`) and what it should say (`now`), and is checked every run:
applied, retired (fixed upstream, so the entry can go), conflict, orphan.
So corrections can be made in MyHeritage at leisure, and the side file
shrinks as they land. The format is in `errata.py`; person facts are keyed
but not applied yet.


## The tree store

`tree_store.py` keeps the tree and the genetics with equal standing in one SQLite file:
the tree (people, families with pedigree type, events, sources, citations;
everything else kept verbatim as GEDCOM subtrees and written back) and the
genetics (kits as tree persons, matches optionally linked to a tree person
with who confirmed it, totals, segments, the painting). It is not an
assertion log: one current value per thing, editable in place, every row
with an `origin` (import or edit) and every edit or re-import clash written
as a readable note. Re-importing a newer export updates imported rows and
keeps edited ones; when both changed the edit wins and the clash is noted.
The database is rebuilt from the GEDCOM, the pipeline's outputs and
`tree_edits.json`, which holds every edit. Round trip on a 3,170-person
export: no person, name, date or parent link changes.

Places enter as their own import (`place_store.py`): the gazetteer's
parishes and places become rows with readable ids (most farms have no
Wikidata item; the QID and archive code sit in columns), parishes outside
the gazetteer come from the parish list, and every event with a place (or a
MyHeritage residence address) is linked through `explain_plac`, else to a
town or region looked up online and cached privately. `event.place` is
never changed. Not yet: validity dates and county or härad at an event's
date.

`gedcom_io.py` follows only biological links for genetics; adopted and
foster links are kept and flagged. People with no family link to the
proband (islands where MyHeritage users build hypotheses) have no lineage
code and their names would only collide with matches', so they are dropped
unless `[gedcom] keep_unlinked`.


## Views

Three linked views whose state lives in the address bar, so any view can be
bookmarked or opened from another (the scheme is in `geoview.py`):

- **Family** (`familyview.py`): one person in focus (`#p=<store id>`,
  default the proband); click anyone to move the focus. Five sections:
  - the pedigree four generations up, drawn above the focus (a row per
    generation, so time runs down the page), each ancestor with years, lineage
    codes (every path under pedigree collapse) and, on hover, counts of
    events, citations and matches whose path ends at them; a parent the
    tree lacks is an empty parent slot, and a person it has without a
    name (whatever it wrote for one: "okänd", "NN", "?";
    `tree_store.name_parts`, also in Geography) a dashed box, "name
    unknown", or a pale gap where the given name is;
  - their families, in the order the books list a household (head,
    spouse, children by birth): parents and siblings (a parent's other
    unions folded), and partners and children, one block per partner,
    each child unfolding to their descendants. Each union is described as
    far as the data goes: married (else the children's years), the ages
    then, how long it lasted and how it ended (a divorce or the first
    death). A union stands until a divorce, or until either partner
    begins another (married or with a child) after its last child; many
    couples have no marriage record, so a passing union shows only by
    what came after it, and no end is claimed for one that did not stand; a child born after a parent's death is flagged, most likely
    belonging to another union. Families, not households: where a person
    lived, a widow in another family's cottage included, belongs to their
    life events;
  - life events by year with their age: the person's own, then derived
    ones, computed from the family and drawn lighter (a parent's, a
    sibling's, a partner's or a child's death; a child's birth or
    marriage; the first grandchild and the first nephew or niece, or
    "born an aunt" when some were born first), kept
    within the person's lifetime, to the day where both dates allow. A
    partner's death is named by the union: husband or wife while it
    stood, "former" after it ended, a passing partner (one child, then
    someone else) not at all; a half-sibling is named so. A derived event that looks wrong points
    at a wrong link in the tree. The death carries a notice: from the
    union standing at death, the partner left behind, or the one joined
    (with the year), or "married to" when that partner's death is not
    recorded; marriages left behind ("former", or "earlier" when that
    spouse's death is unknown); the children, by partner when there were
    several families, and grandchildren born by then; and the siblings who survive (or "the
    last of n siblings"). Each sibling's death says how many are left, and
    the parents' family line how many children are living: someone born
    less than 120 years ago with no recorded death is presumed living, so
    an unrecorded death shows up as one too many;
  - the references in the shared order (span, archive, series), repeats
    counted, other trees' citations only counted; the heading opens the
    person's citations in Archives (`#person=`), and each volume, on
    hover, everyone in it;
  - the descendants: a row each, partners under the person (⚭, paler
    when not married), children under their union, generations indented,
    every life a bar on the section's own time scale with decade lines;
    counted per generation, open down to the grandchildren, who show
    folded (fewer past 250 rows); ▸ left of a name unfolds that person's
    partners and children, whichever partner the descendant is; someone
    reached twice is marked ↺.

  The first lens (roadmap: lenses on one focus).

- **Geography** (`geoview.py`): every located tree event (from the store)
  and household-examination citation (one point per person, volume and
  page, at the farm or village of record, else the parish), with facets as
  in a tag browser: time, layer, event type, branch, precision of place and
  date, parish, person. A chosen person's "+ spouse" adds the spouse and
  draws both lives as numbered paths. Clusters show their colour mix as a
  ring and name what their points share ("Hagelstorp +1"); residences show
  as stays; dates are shortened (~1850 about, <1850 before, 1850–1860
  between or a volume's years).
- **Archives** (`volumes.py`): parishes with archive codes and Wikidata
  items, farms with every cited volume and page, a parish's volumes by
  series page by page, and one volume's farms coloured by page.

`places_rules.py` shows every normalisation with live examples, so the page
cannot drift from the code, then the family's hand rules and which rule
resolved each place string (that part private).
