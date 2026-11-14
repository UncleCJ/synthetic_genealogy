# Roadmap

What comes next, roughly in order. Terms are explained in
[concepts.md](concepts.md); the current modules in
[architecture.md](architecture.md).

## The golden path

A direction, not a finish line. The evidence keeps accumulating: DNA is
carried by the living and by every new generation, and the archives hold a
wealth of records waiting to be read. The project turns what the family
still carries into meaning: who our ancestors were, where they lived, how
we are related, each claim with its evidence and its doubt.

What draws us to genealogy is also what keeps the work going: curiosity
about the people, a puzzle solved, a relative found. So each step should
aim to result in something we can see and enjoy.

Waypoints, in order:

1. One codebase on shared concepts (now).
2. A lens in place: one person or one match, seen and used (next).
3. A second family runs it unchanged.
4. A genealogist who isn't us follows one documented route, from a GEDCOM
   and a few kits to the lenses.
5. The big questions answered with it, the contested paternity first.

The test for any task: does it bring the next waypoint closer? If not, it
is parked, not dropped. Confusion and fragmentation are what the path
avoids; "How we work" in [concepts.md](concepts.md) keeps them off.

## 1. One coherent codebase

The unifying idea is already written down: the three kinds of state
(received, kept by hand, rebuilt). Every module should read received or
hand-kept state and write only rebuilt state. The guiding concept for the
genetics is **phasing as belief, not a step**: each donor has a copy
model, a fuzzy belief per stretch of each copy about which ancestor it came
from. It starts near blank, works with a single donor, and is sharpened by
whatever evidence exists. Evidence is assertions of one shape (subject,
assertion, interval, source, asserted_by, weight, date); tree links and DNA
Painter paintings have equal standing, weight follows evidence quality, and
one match counts once however many sources name it. Lineage paths are kept
at full depth, not truncated to two letters.

**Round 1: foundations** (done, 2026-11-10): an interval type with a real
genetic map (`intervals.py`, HapMap II GRCh37); synthetic scenarios
(`simulate.py`); one assertion record and identity module (`assertions.py`,
`identity.py`, `lineage.py`); hand-kept assertions in
`data/notes/assertions.toml`; the genetics steps' tables through the store
(`outputs.py`); prospects without the mother. Still open from it:

- reading errata, store edits and research entries as assertions
  ([#2](https://github.com/UncleCJ/synthetic_genealogy/issues/2)); a new
  tree accession compared with the last by meaning (concepts.md), with what the tree no longer
  says retracted rather than deleted, and the store's own person ids,
  never reused, with GEDCOM xrefs and vendor ids as keys of stated
  strength (`identity.py`); a citation's raw text kept as received and
  the reference reader's reading of it as an inferred assertion carrying
  the reader's version;
- interval sets: `intervals.IntervalSet` per chromosome (union,
  intersection, difference, bp and cM measure, longest stretch) exists,
  with no caller yet; the sibling-shared checks use `jaccard`; sets on one
  copy wait for the copy model's beliefs, and whether they are stored or
  recomputed is open;
- dropping the child/mother roles and the mother slot in `kits.py`
  (placement is built on them);
- FTDNA ICW lists in the shared-match graph (FTDNA keys are names);
- confidence in the DNA Painter round trip, and GEDmatch validation for any
  donor pair, from the copy model's beliefs.

**Round 2: the new core** ([genetics.md](genetics.md))

1. The copy model. Done: single donor and phased siblings, calibrated,
   segment ends as crossover votes, placement through it by default, sides
   from phased siblings, deep labels read back, distinctive-surname joins
   counted as confirmed. Recursive deduction for one grandparent works on
   the simulator; on real data it waits for donors through her mother.
   Open:
   - deeper labels need confirmed identities on deep paths (`deep_labels.py
     --confirm` lists the joins worth confirming), or a footprint prior
     (section 7);
   - recursive deduction for every grandparent and at depth 4;
   - placement in two halves (side, then grandparent); `revelations` as
     runner, `match_placement` as library;
   - replacing `phasing_labels.label()` once the painting is no longer
     needed as a reference;
   - sparse regimes (single donor, no parent or siblings; findings in
     genetics.md): `copy_model.match_branches`, a per-match branch
     posterior by joint path probability, for match reports and prospects
     only, never as assertions; absence from close relatives with a
     complete export as lineage assertions (the gap rule); a sparse
     scenario in the simulator, with `EVIDENCE` calibrated per regime;
     still to test: a half-sibling as phasing partner, an unknown
     half-sibling's side from sex-specific maps, coverage per added
     anchor, findings on genotype-level virtual kits, pedigree collapse;
   - absence from a mother's one-to-many file counts only with
     `same_selection` (2026-11-12); later inside a complete panel, computed
     from the accessions (concepts.md, Scope and panel). Since 2026-11-13
     it counts only from 10 cM and for matches first seen (any donor's
     accession) by the mother's list date; FTDNA match dates are read,
     MyHeritage has none.
2. A pipeline driven by the data available: steps declare needs and
   outputs and skip rather than fail; `--without <person>` runs for
   validation; an explicit fixed-point loop instead of running twice.
   Later at the level of assertions: a new one marks what was computed
   from it stale, what lacks inputs waits rather than fails, and the
   result does not depend on the order evidence arrived in.
   Meanwhile `--keep-going` lists failed steps, and placement runs without
   a painting from the copy models and relatives at a known path
   (`[[placement.relatives]]`); on one such family 15 of 22 steps run, the
   rest lack data and should skip.
3. Sharpeners: the HMM for any n ≥ 2 siblings with an optional parent; a
   twin-cousin or half-sibling kit; an "at least half" sibling kind
   (concepts.md) settled by shared cM and fully identical regions; sibling consistency as "same copy"
   links instead of a painting editor; a relatedness check for kits whose
   sharing doesn't fit their stated relationship; relationship odds
   calibrated against the Shared cM Project, with population IBD for
   distant relationships.

**Round 3: the rest**

4. Pile-up masking in placement; the X chromosome model; the records
    tools (`volumes`, `gazetteer build`, `geocode places`, `residences`) as
    pipeline steps (places a build adds have no coordinates until
    `geocode.py places` runs, so their events sit on the parish point); a
    shared view helper for the HTML views; output descriptions in `serve.py`
    supplied by the writing step; the showcase check through the identity
    module.

    Views as **lenses on one shared focus** (proposed 2026-11-12): a group,
    one person, or a comparison set of two to five. Each lens draws one
    shape (map, graph, timeline, segments, documents), never calls another,
    and edits only by writing assertions, so undo is retraction. One lens
    per concept (one records view, reached from everywhere); counts first,
    detail on demand; uncertainty drawn the same way everywhere; empty
    lenses hidden; every state addressable by URL, as the two views are
    today. Before building one, a design on paper per lens (focus, what it
    draws, what it reads, which assertions it writes) gives the list of
    questions the store must answer, and rounds 1 and 2 are checked
    against it.

    The views (Geography and Archives; [records.md](records.md#views)).
    Open:
    - The life path, to be cleared up as a concept: what a person's path
      is (which events and records, stays or entries), how year-only and
      undated events are ordered, how a stop is numbered, and how
      precision shows. Today the geography view draws dated tree events
      only, numbered per run of one place; the dropped People view's
      life map (`lifepath.py`, in git history) also drew record stays.
    - Back and forward as undo, the same in every view: a change to what
      is looked at (focus, a filter) adds a history step; a change to how
      (pan, zoom, folds, open facet groups) replaces it, kept in the
      address. Today Geography and Archives replace on every filter change
      and the family lens keeps folds out of the address. Also a link from
      Geography's person facet to carry on with that person in the family
      lens.
    - References in one order everywhere, computed, never stored: by
      span (first, then last year), then archive name, then series in
      the archive schema's order (records.md), lowest precedence.
    - The family lens (2026-11-13) walks relations and lineage paths, read
      only, with households, life events and references; open: the person
      section as a life narrative (the life path below), references tied to
      the claims they support (span against events), comparison focus,
      the contested parentage drawn as rival parent slots, household
      entries linked child to adult. The People view's lifeline (volume
      years per parish, gaps, moves) could return in it; until then
      `residences.py` lists the gaps. Since 2026-11-13 it says how the
      focus is related to the proband (shortest path, blood before
      marriage) and draws household lifelines; the lifeline column narrows
      the names. Open, for keeping the shape in sight while walking:
      relatives coloured, paler, by where their branch leaves the
      proband's line, and people reached by marriage dashed or plain;
      people reached only by marriage and with no matches or sources
      dimmed, as candidates for pruning in the master tree; an overview of
      where the focus sits beyond the four generations shown.
      The union web (people joined by partner links: a widow's next
      husband, his late first wife, step-siblings), sliced at a date by the
      unions standing then, as the household the examination books should
      show; the lens still says half-sibling where the kind is open.
    - **Fading** (proposed 2026-11-13; "fog of war" without the fog):
      what lies off the focus's own dimension, such as an in-law's family,
      shown only partly and lighter, so a layout can spread the tree over
      time and space without drawing all of it. The same weight could
      carry certainty (vague dates, unsourced events, the older records
      where names blur into spellings and possible confusions); whether
      one fade can honestly say both is open.
    - **Spreading the mesh:** drawing the tree on a time axis rather than
      by generation, so the drift shows (a cousin's children can be older
      than the proband); the household lifelines are the local first step.
    - Errata as the to-do list for the master tree: an applied erratum is
      a fix still waiting in MyHeritage, and it retires itself on the next
      export, so no editing interface is needed. Open: facts about a union
      (a divorce, a marriage date) have no key yet, and the lens neither
      marks a person with open errata nor lists what waits upstream.
    - Hand edits from the command line (`tree_store.py` subcommands, man
      pages in docs/man/): additions in the store, corrections in errata.
      Open: people and families have no edit command
      ([#1](https://github.com/UncleCJ/synthetic_genealogy/issues/1)); citations
      that lose their event on a re-import are only logged
      ([#3](https://github.com/UncleCJ/synthetic_genealogy/issues/3)).
    - Architecture pictures for packaging the views (say as an iPad
      app): one diagram per question (data, views, what runs where), none
      yet beyond the layer sketch in architecture.md.
    - Family and Archives searches fold Swedish spelling variants
      (`geoview.name_fold` / `FOLD_JS`). Later: a place search could also
      list matching people (linked to the family lens, or to their
      places); left out for now to avoid clutter.
    - How the views get their data, to consider closely before the lenses
      multiply (for now each view embeds its own, concepts.md): one data
      file or store export shared by the views, a backend over the store
      (lenses that write assertions need one), or the views melded into
      one page. Each changes the deployment contexts in data.md, so it is
      decided, with its assumptions, before it is built. Archives' data
      repeats parish and volume strings on every row (it gzips about 25
      times smaller).
    - An archives panel in the geography view: the volumes and pages of
      the parish or place in view, beside the map. Both views are built
      after the steps they read (volumes, store, places), a second stage
      once the pipeline drives the records tools.
    - Family branch as a drill-down, generation by generation: M as the
      superset of MF and MM, MF of MFM and MFF, and so on (today one
      grandparent branch at a time). Ancestors already carry their full
      lineage codes; relatives carry only the grandparent branch of their
      closest shared ancestors, so deeper levels need that path at full
      depth from `volumes.kinship`, and pedigree collapse puts one person
      under several codes.
    - Lineage colours (2026-11-13/14) come from one scheme in
      `lineage.py` for every view and plot. Hue says where in the tree:
      each code owns a sector of the HSL wheel holding its ancestors'
      sectors (F from 225°, M from 45°); a person keeps a share of it
      that grows with the generation (`OWN_SHARE`, tuned by eye in a fan
      chart) and the parents split the rest, the same-sex parent first,
      so the straight lines stay opposite. OKLCH lightness says how far
      back (older fades), a father is a step darker than the mother, and
      dark yellows are lifted so they don't read as brown. The family
      lens colours each ancestor by full code (colours computed at write
      time); the other pages carry only F, M and grandparent colours
      (`lineage.css_vars`). Open: pedigree collapse gives one person
      several codes, and the lens takes the first; relatives off the
      direct line carry no code, so no colour; unvalidated past five
      generations.

Then a package layout and `pyproject.toml`, laid out by the layers this
work produces (not chosen in advance; with about 40 flat modules,
setuptools auto-discovery would make `pip install .` fail today). With it,
move `research/README.md` to `docs/research-log.md` and drop the fallback
in `research_log.py`.

## 2. The contested paternity

The first use case. A great-grandmother's father denied paternity while
acknowledging her older sisters; records survive, descendants of all the
sisters can test, and one match descends from the named man's family.

1. Phase a sibling set of her descendants to grandparent level, and anchor
   each chromosome's side and copy labels with known cousins.
2. Phase one generation up: her children, represented by their donor
   descendants, separate her two original copies.
3. The sister test: acknowledged sisters' descendants matching on both of
   her copies means full sisters; on one copy only, maternal half-sisters.
4. Check the match from the named man's family against a prediction: its
   segments must fall on her paternal copy, in exactly the cousins who
   carry that copy there.
5. Write it up: a likelihood ratio for full versus half sisters from the
   second-cousin amounts (siblings' totals are not independent), a
   hypothesis page weighing DNA and letters, and a calibration of how many
   donors make it decisive (Ped-sim or msprime on the actual pedigree).

## 3. Data

Run the readers on the remaining archived exports; check chip overlap for
the raw kits; recruit donors on each line the use case needs; a rerunnable
manifest of the cloud archive (type, date, size, which reader).

## 4. Model gaps

Sex-specific genetic maps; endogamy; an exploratory per-copy match-space
view (Jaccard on cM intervals, pile-ups masked). The interval engine, the
X chromosome and pile-up masking are in section 1.

## 5. The second case

Linnea's unknown father, with the same tools and its own config
(`FAMILY_CONFIG`).

## 6. Places as dated assertions

Done ([records.md](records.md)): one place-string resolver in the
gazetteer, a full parish list from Wikidata, short and old forms, places
shown with their whole hierarchy, one reference reader, Riksarkivet's
volume facts from each archive's inventory, and places abroad skipping the
Swedish rules. Open:

- **Parishes, congregations and towns as separate entities** (decision in
  concepts.md, model in records.md): harvest all Wikidata items per cited
  archive code, with dates, dated codes and successions (archives with more
  than one item are the Gränna-like cases); tag cached volumes by the
  congregation their notes name; split Gränna and review the odd keys
  (town names, regiment and castle congregations, the dated key); a
  resolver that returns candidates narrowed by date, volume and farm, else
  the archive; then the downstream tools, maps and tests. Cross-check with
  Skatteverket's "Sveriges församlingar genom tiderna".
- Two parish rules remain: `volumes.normalise` (`PLAC_SUFFIX`) and
  `Gazetteer.parish_rule` (`PARISH_SUFFIX`); join them once the gazetteer
  is built as a pipeline step. They still assume the family's citations
  name every parish ("Östra Eneby" against the key "Norrköpings Östra
  Eneby"; "till Maria Församling" read as a parish).
- Wikidata's counties are today's; missing historical aliases on Wikidata;
  county and diocese at an event's date; TORA for farms; Norra Ryr is not
  in the parish list.
- Kommuner (noted 2026-11-12): the "town" level mixes stad, kommun (1971-,
  earlier landskommun and köping) and post town. On two families about 900
  events name a parish that is also a kommun (read as the parish, right only
  before 1971) and about 600 a kommun that is no parish; labels go wrong
  where a name is several ("Ringv. 14 C, Tranås" given Skåne). Plan: each a
  level of its own, each församling's kommun from Wikidata, a postcode as a
  clue to its kommun (GeoNames) rather than dropped; after the Gränna
  split. Drafted on the branch `claude/town-parts-wip` and set aside: a
  town after a parish without a comma ("Lundby Göteborg"), a bare town
  over a namesake farm ("Malmö").
- The archives view without the place hierarchy.
- Places abroad: a country facet in the geography view; foreign parishes
  (Danish sogn) as places of their own.
- Riksarkivet: check the guessed image for a page (uppslag versus pages);
  volumes without a page span.
- Register OCR without cloud AI (`experiments/register_ocr`, one volume):
  page numbers, farm-index pages and names read; birth years not yet.
  Next: cache each volume's structure (image→page, farm index, form) as
  public facts, person hits and crops privately; it replaces the guessed
  image. Bulk fetching waits on Riksarkivet's terms.
- A public reference layer beside the gazetteer: a source ontology of
  record types (births and baptisms, marriages, burials, household
  examinations, moving records, estate inventories), each with its era,
  typical fields and archive URL pattern (burial records are a blind spot
  so far); kommuner and historical counties as dated entities with dated
  "part of" relations, linked to Wikidata and OSM, disambiguated by date
  and context, never by name alone. One shape for every level (level,
  years, dated names, part-of and became links); a name returns
  candidates, never one unit; farms get dated part-of links only where a
  change has been met. Kept as plain text in the repository and built
  into a store of its own, which private data refers to and never the
  reverse; spelling variants learned from a family's tree go public only
  through the gazetteer's reviewed proposals.
- Review the gazetteer proposals; apply person-level errata in `gedcom_io`;
  collate stays and open the gap volumes `residences.py` lists.
- Reading errors: the long s (ſ) read as f, as p, or beyond recognition
  (-hult names suffer most). Candidate checks, unvalidated: f→s before
  s/h/t giving an existing name in the parish; an edit-distance search
  against TORA or OSM names in the parish; a parish lookup that falls back
  to `ortho()` on a unique hit. Old f for v (Kalf-, Hof-) stays a hand
  rename, since a general rule would break names like Rolf.

## 7. Geography of matches

Next to explore. Joining DNA to places directly: every lineage path
has a **footprint** (the dated places of the ancestors on and above it,
from stays, events and volume citations), so any DNA assertion that names a
path inherits one: a placed match, a cluster, a prospect whose tree-linked
shared matches carry deep codes, a stretch of a copy. "Side F, branch FMFF"
becomes "these three parishes, about 1780–1820, and these volumes to open".
A shared ancestor can sit at or above the node a shared match points to, so
a footprint includes the ancestors above.

Three questions it should answer:

- **Where to look** (match or cluster → parishes): weight each path its
  evidence supports by shared-match support, one match counting once; take
  a time window from the expected generation depth (cM → relationship →
  birth decades); rank parishes, and farms where precise, within it; end in
  the volumes `volumes.py` and `residences.py` say cover them.
- **What points here** (parish → DNA): its ancestors, their lineage paths
  and copies, and the matches and clusters pointing there; places with many
  matches but few cited volumes show where knowledge is thin.
- **Consistency:** a match whose segments say one branch while its shared
  matches point to another branch's parishes is worth opening; cross-side
  shared-match links should sit where two branches' footprints overlap
  (pedigree collapse, local endogamy), or they point at misplacements.

First experiments, a throwaway script over the store (2026-11-12, findings
in the research log): branch footprints differ strongly (Jensen–Shannon
distance near 1 between most great-grandparents), so geography can
discriminate. Parishes ranked from tree-linked shared matches alone hit
the hidden match's ancestral parishes in the top 3 for 71% when no shared
match sits on the same path, against 30% for all ancestors without DNA;
but only 20 matches could be tested, the hit was lenient (any parish of
the couple), and grandparent-level placement ranked nearly as well.
Cross-side links showed no footprint overlap. Before a pipeline step: a
stricter test (one parish, paths of 4+ letters, against the grandparent
ranking) and more matches in the shared-match graph.

Built properly it needs: geographic assertions as assertions (a hand-kept
one, such as a match's own ancestral parish, is weak evidence for placement in turn), footprints as place × fuzzy time
intervals, footprints computed from the store, full-depth lineage paths,
and views (a matches layer in the geography view, a parish-hints column in
prospects, links from `match_view`).

Caveats: parishes as the unit, farms only where precise, at the event's
date (section 6); little resolution if every branch lived in the same few
parishes (experiment 1 says when); soft time windows; matches' own trees
are mostly unavailable. Match-level maps stay private, since matches are
living people.

## 8. Simulation on the actual pedigree

Ped-sim (read by `simulate.from_pedsim` since 2026-11-12) or msprime's
fixed-pedigree mode on the pedigree from the tree store: many simulated genetic outcomes of one known pedigree, with
crossovers placed by a genetic map. It would calibrate today's judgement
calls (the 7 cM floor, the short-block rule, the mother-window rule, the
anchor weights), give the sister test its power and the cM distributions
for a full- versus half-sister likelihood ratio (simulated jointly, since
siblings' totals are not independent), and feed the synthetic test
scenarios. Vendor detection (thresholds, false segments, phasing errors)
must be simulated on top, or the results flatter the method. After the
store becomes the hub; start with a short tutorial for CJ before any design.

## 9. Agents as scoped tasks

A task is a bounded hypothesis: which parent slots, how many generations,
which sources, what counts as done. Findings come back as assertions
marked agent-sourced, with citations and confidence, into a review queue;
nothing counts until CJ accepts it, and rejections keep their reason. Same
read and write path as everything else. Delivery stays open: reports,
served pages, batch runs and notebooks are renderers over the same
queries. Segments stay typed rows with a shared provenance id, and
aggregates (totals, clusters, triangulation) stay derived.

## 10. Parked

Hypotheses as computed objects (likelihood ratios beside documents; after
simulation); structuring records from images (handwritten-text recognition
of household examinations into proposed stays); ideas from the 2020 gist
not carried forward (match metrics such as SNP density, age as a
constraint, patronymics, causality, ancestry composition, cultural
heritage).

## 11. Earlier ideas, not started

Verify the unverified export formats with real samples; a triage and group
interface; an existing tool as a host for the inference engine instead of a
new application; Gramps or Wikibase as the store of record.

A provisional Wikibase mapping (2026-11-12; a separate Wikibase thread's
conclusions, when written up, take precedence): entity → item; assertion
type → property, whose datatype is the value schema (so the property list
is the predicate registry); assertion → statement; provenance → references;
weight and rivals → ranks and qualifiers; valid time → start, end or point
in time; recorded time → revision history; an empty parent slot → father or
mother with "unknown value"; derived values → computed at query time;
gazetteer → links to Wikidata. Bulk genetic data would stay typed rows
outside Wikibase, with statements only about it (placements, identities,
hypotheses). Crack to check first: how the assertion's interval and
independence group map (qualifiers, a reference property?).

Occupations as a focus of their own (2026-11-13, tentative): browse
everyone with one occupation ("all snickare"), from occupation events and
household-examination titles, with spellings normalised and each title
dated, as places are; a context link from a person's occupation keeps
them in view.
