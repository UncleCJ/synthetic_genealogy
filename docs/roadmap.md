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
     (section 8);
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

**Order for the genetics** (from a review of the models, 2026-11-23,
kept as a private doc): the binding constraint is the
observation model (what a vendor reports, given the true sharing), not
the inference model.

1. Vendor calibration from the donors' own pairs. A parent–child pair
   shares one copy end to end, so every interior break it reports is an
   artefact. A first look (one pair per vendor, four exports): MyHeritage
   reports one or two false breaks per parent–child genome, most of them
   mid-arm, where the centromere rule doesn't reach; FTDNA none. On a
   sibling pair both cover, totals agree within 0.2% but the segment
   structure differs; FTDNA's cM run 2–3.5% higher. Wanted, over every
   pair and both vendors: the false-break rate, an asymmetric end model
   and a per-donor artefact mask. With it, nested rows in the readers:
   FTDNA lists a close relative's fully identical region as a row inside
   the half-identical one, and `edges.py` takes every row as a segment,
   so it counts them twice and votes their ends as crossovers.
2. The deep-crossover test (two-way end clusters as crossovers beyond
   the grandparents), on candidates masked by 1, kill criteria as set.
3. Simulation-based inference for the contested paternity (sections 3
   and 9), in parallel: the sister test works at depths 1–3 and needs no
   deep crossovers, so it is the hedge if 2 fails.
4. Per-segment nulls from the donor's own genome: how common the donor's
   haplotype is over a segment, observable without the match's genome.
   Kill test: do the copy model's leave-one-out dissents and the
   painting's misses gather where the haplotype is common?
5. Interval emissions and a per-export observation model in the copy
   model (`END_CROSSOVER` is a fixed 0.5 today), measured by 1.
6. Independence groups per cluster, and path reliability per letter.
7. The parish ranking scored by distribution distance (section 8).

Open: whether the archive holds an FTDNA 2020 export at the 1 cM floor
(then the Build 36 lift-over matters); whether the mid-arm breaks are
dropouts, imputation holes or regional (a mask per donor, chip or
region); whether nested rows occur for distant matches too; how much
end-cluster evidence survives the mask (enough candidates for 2?).

**Round 3: the rest**

4. Pile-up masking in placement; the X chromosome model; the records
    tools (`volumes`, `gazetteer build`, `geocode places`, `residences`) as
    pipeline steps (places a build adds have no coordinates until
    `geocode.py places` runs, so their events sit on the parish point); a
    shared view helper for the HTML views; output descriptions in `serve.py`
    supplied by the writing step; the showcase check through the identity
    module.

    The views and their focus: section 2.

Package layout done 2026-11-23 (`sg/`, architecture.md). Open: a
`pyproject.toml` (the top-level launchers and runners are not in the
package, so `pip install .` would need them listed or moved). With it,
move `research/README.md` to `docs/research-log.md` and drop the fallback
in `research_log.py`.

**Refactoring** (proposed 2026-11-23; about 60 modules, 20,000 lines),
each step on its own and behaviour unchanged:

- Done 2026-11-23: packages from architecture.md's sections (`sg/`),
  launchers at the top level for the tools run by hand.
- Done 2026-11-23: the four pages' HTML and JS in `sg/views/pages/`
  (`<page>.html`, `<page>.js`, shared snippets in `shared/`), read by
  `viewkit.template`; scripts syntax-checked in the tests. Still in
  Python: the generated fold JS, the loader, the nav CSS, and the HTML
  that `match_view`, `locus_view` and `places_rules` build in code. A
  `pyproject.toml` must ship `pages/` as package data.
- Done 2026-11-23: `volumes.py` split; kinship is `lineage.kinship`, the
  Archives page `archivesview.py`, the `home` and `farm` reports
  `homes.py` (still run as `volumes.py farm|home`).
- One parish rule instead of two (section 7), once the gazetteer is a
  pipeline step.
- Later, with `pyproject.toml`: one `sg` command with the hand-run tools
  as subcommands, matching the man pages.

## 2. Views: focus, lenses, links

Six pages today (Family, Geography, Archives, Genome, the match report,
the locus view) and the shelf's image viewer; [lenses.md](lenses.md) reads
them through the model (focus, lens, page, overlay). Each page chose its
own focus and address, and they link to each other unevenly. This section
holds what they share and what comes next; the last part orders it by
effort.

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
against it. Since 2026-11-14 the model separates lenses (one shape)
from pages (lenses sharing a focus) and adds overlays keyed by person
or lineage code ([lenses.md](lenses.md)); Family is a page, and its
tree lens is pulled out when a second page needs it.

### Focus selection

Proposed 2026-11-23. A focus is a set of things of one kind, chosen by
rules. Geography's facets choose events only, and only by the event's own
values: `type=birth&place=Källeryd/Hagelstorp` draws the births at
Hagelstorp, not the people born there with the rest of their lives, and
nothing can ask how far someone moved or where they were last seen.

**Kinds.** Received or kept: people, events (a person at a place and
date), places, volumes. Derived, computed in the pipeline as rebuilt
tables, never kept:

- **Steps:** consecutive places on one person's life path, with from, to,
  years, the time between and the distance (great-circle between the
  place points; a parish point makes it approximate, and says so). "Moved
  more than 30 km" is a rule on steps.
- **Loose ends:** where a path stops without a death or burial: the last
  dated place, the year, the age then, and whether the volumes that would
  continue it (the next household examination, the moving records) exist
  and are open. Ranked by nearness to the proband and by how
  answerable they are, they are leads, not errors; an emigration note
  ends a path with a known continuation.
- Later: gaps (a stretch of a path between two records, `residences.py`
  today) and the union web's households at a date.

Both wait on the life path as a concept (Geography, below): which events
and records make a path, their order where dates are vague, and how
precision carries into a distance.

**Rules.** A rule names a kind and a condition on its values, or on a
linked kind through person, place or year: people by their events (born
at a place, any level of the hierarchy, a year span optional), by lineage
code, by descent from a person to a depth, by surname with its variants,
by occupation, by linked match or kit, by open errata, by an event
without a source; places by their people (where a line lived); steps and
loose ends by their person and by their measures (distance, years, age).
Clauses joined by "and". A person focus is a people rule of one.

**Select or mark.** A rule either narrows what is shown (select) or
highlights within it, the rest faded (mark): select the ancestors, mark
their steps over 30 km; select a branch, mark its loose ends before 1900.
In the address: `sel=` and `mark=`, each `<kind>:<rule>`, e.g.
`sel=person:born@Källeryd/Hagelstorp`, `sel=person:line@FMF`,
`mark=step:km>30`, `mark=end:year:-1900`. Today's facets stay as the
event filter under a selection.

**Where it runs.** Derived kinds and their measures in Python (a module
beside `stays.py`, reading the store and the gazetteer), written as
rebuilt tables, so the pages only compare values; one rule parser in
Python (page writers, `store_query.py select <rule>`) and a JS twin
emitted from Python (as `FOLD_JS` is), tested on the same synthetic
cases. Descent and ancestry rules need parent links on the page, which no
view embeds today: the first case for a shared people table (below, how
the views get their data).

**Named selections** once a rule is reused: hand-kept
`data/notes/groups.toml` (name, rule, note), offered as a menu; a
hand-picked list (the comparison set) is a rule of ids.

**Counts first:** a selection opens on its size, year span, main
parishes and branches, and how many have sources and matches; steps on
their distances, loose ends on how many are answerable.

**Pages** that take a selection: Geography (people's events, steps as
arrows, loose ends as open markers), Archives (the volumes covering the
places and years, and the volumes that would close loose ends), a
timeline lens (lifelines by birth), Genome (matches whose path ends in
the people). Family keeps a person focus but can mark the selection's
members.

**Order:** people rules on Geography (born, lived, died at; lineage
code), with `sel=`/`mark=` from the start; then the life path settled
and steps with distance; then loose ends with the volumes that would
close them.

State (2026-11-23): people rules in Geography, `sel=` and `mark=`
(`pages/shared/rules.js`, tested with node on synthetic people): born,
died, married, lived or any event at a place (any level of the
hierarchy) or in a year span, lineage code, relationship, surname,
name; `!` negates, `a|b` either. Place popups link the people born,
living or with any event there. Steps and loose ends since 2026-11-23
(`lifepath.py`, which settles the life path: a citation dated only by
its volume stands back for a better-dated point at the same place, a
burial is no step; `step:` and `end:` rules,
drawn as lines and open rings; a loose end says whether the parish has a
later household volume, from the offline inventory cache, and leads
with one the person or their household is cited in). Open: the
Python twin and `store_query.py select`; named selections; other pages;
descent rules (need parent links on the page); steps summed per parish
pair; loose ends in Archives and the work list; the cache holds
inventories only for archives once looked up.

### Linking

Proposed 2026-11-23. Family links to Geography and Archives; Geography
and Archives to each other and to Family; Genome to Family; Archives and
Family to the shelf (⌂). Nothing links to Genome, and the match report and
the locus view are reached only by hand.

- Done 2026-11-23, in part: `pages/shared/links.js` (`linkTo`) builds
  each view's address from a focus (person, parish, lineage code, rule)
  and the nav bar carries it; the links inside the pages still build
  their own addresses (moved to `linkTo` when next touched).
- Every mark that names a person, place, volume, lineage code or match
  links to the page for it: a click moves there, a context link
  (glossary) keeps the current page.
- Done 2026-11-23: the nav bar carries the focus where the target takes
  it (a person on Family opens Geography on their path, Archives on
  their references, Genome on their code; a rule carries to Geography).
- Missing links, first: Family → Genome per person with linked matches,
  and per ancestor once the ancestor focus exists; Genome → Geography (a
  match's tree path as a footprint, section 8); the shelf viewer → the
  people citing a page.

### Geography

Refinements (proposed 2026-11-23), roughly in order:

- Selections as its focus (above): `sel=` and `mark=`, steps as arrows
  (marked over a distance), loose ends as open markers; the facets keep
  filtering events.
- One row is one event: a marriage drawn once with both spouses, so the
  histogram and legend count what the table counts.
- Place precision drawn: a farm as a dot, an event placed on its parish
  point as a ring, so a cluster at a church isn't read as a village.
- Time as a control: a year scrubber showing who was where in a window
  (stays and events), the rest faded, as the lifelines read.
- Steps of a selection summed per parish pair: where the people born
  here went.
- A place card on click: hierarchy and dated names, the people there by
  decade, the volumes covering it (the archives panel below), links to
  Archives and the shelf.
- A country facet (section 7).

Open from before:

- The life path: settled 2026-11-23 in `lifepath.py` (dated points of
  every kind, in order; a parish point after a farm in it is no move),
  used for steps, loose ends and the person's path on the map
  (`lines=1`, its stops numbered).
- Geography against the lens model (noted 2026-11-14): its focus is
  loose (a group by facets, with a Person facet beside them), and its
  table lists events of mixed kinds: tree events, citations and stays,
  with household examinations shown as such rather than as stays. To
  settle: what one row is, and whether the focus is a group, a person
  or both. The Relationship facet rests on assumptions to revisit:
  ancestors also count as relatives, spouses are taken as not
  relatives although a spouse's family in the tree would be neither,
  and unlinked people are left out for now; "ancestors" could become
  a toggle instead of a value. The Family branch facet is oversimplified
  too: only ancestors carry a branch, so F and M select the parents
  alone, and the proband, siblings and anyone off the direct line fall
  outside every branch. A branch could mean everyone whose kinship
  runs through that line (the drill-down below), with F and M as its
  first level. A relative's branch is the proband's ancestor all their
  paths pass (a paternal first cousin: F), which is how they are
  related, not which ancestral line they belong to; the two may need
  splitting. An adopted relative carries a branch at all, though no
  DNA comes that way (the store keeps the pedigree type).
  "Unlinked" means two things: in `gedcom_io` a person with no family
  link to the proband (dropped at import), in `lineage.kinship` one
  linked but neither a blood relative nor a relative's spouse (a
  half-sibling's mother's family, a spouse's parents). One of them
  needs another name. Branch, Relationship and Surname count people;
  Event type, Parish, Layer and Person count events ("n events"), as
  they split one person's events (the split is listed by hand). The
  time histogram and the colour legend still count points, and an
  event of two people (a marriage) is two points, one per spouse.
- An archives panel in the geography view: the volumes and pages of
  the parish or place in view, beside the map. Both views are built
  after the steps they read (volumes, store, places), a second stage
  once the pipeline drives the records tools.
- Dated map layers under the geography view's events
  (`maplayers.py`, 2026-11-17): Lantmäteriet print-outs (SWEREF 99 TM)
  and ekonomiska kartan scans, one image per layer. Open:
  Generalstabskartan, häradsekonomiska kartan and laga skifte maps by
  control points against the ekonomiska kartan; Lantmäteriet's
  historical orthophotos (1949–2005, a WMS behind credentials, so
  through serve.py); the chosen layers and opacity in the address.
- Family branch as a drill-down, generation by generation: M as the
  superset of MF and MM, MF of MFM and MFF, and so on (today one
  grandparent branch at a time). Ancestors already carry their full
  lineage codes; relatives carry only the grandparent branch of their
  closest shared ancestors, so deeper levels need that path at full
  depth from `lineage.kinship`, and pedigree collapse puts one person
  under several codes.

### The family page

- The family page (2026-11-13) walks relations and lineage paths, read
  only, with households, life events and references; open: the person
  section as a life narrative (the life path, under Geography), references tied to
  the claims they support (span against events), comparison focus,
  the contested parentage drawn as rival parent slots, household
  entries linked child to adult. The People view's lifeline (volume
  years per parish, gaps, moves) could return in it; until then
  `residences.py` lists the gaps. Since 2026-11-13 it says how the
  focus is related to the proband (shortest path, blood before
  marriage) and draws household lifelines; since 2026-11-14 the
  pedigree grows upward and descendants follow the references, so
  time runs down the page, joined by lines in the lineage colours, the
  great-grandparents by given name (full name on hover); the lifeline column narrows
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
- **Context of a life** (2026-11-23): the life events add the moves
  from the life path, each step labelled by where relatives were (step
  labels: back, born, parents, ageing parent, kin, near, together,
  following; Geography writes them to `life_steps.json`); the parents'
  moves, siblings' and children's first moves out; siblings' weddings
  (the same day marked), a parent's new marriage, cousins married the
  same day; grandparents living at the birth and left at each death.
  Remarks read from the person's rows (rows(1)) show beside the moves.
  Household role from the row titles (rows(1): in service, lodger,
  undantag, elders in the household). Open: household size beyond a
  rough count (farm headings to split households; titles boxed apart);
  care of elderly relatives beyond the few elders read; neighbours (tree people on
  adjacent pages); the parish's own context (epidemics in the death
  book, famine years); the quick back-and-forth steps left (127, from
  the tree's residence entries) as fix notes.
- **Spreading the mesh:** drawing the tree on a time axis rather than
  by generation, so the drift shows (a cousin's children can be older
  than the proband); the household lifelines are the local first step.

### The genome lens

The **genome lens** (design in
[lenses.md](lenses.md#design-on-paper-the-genome-lens)): one segments
lens with donor, ancestor, match and locus as focus kinds, reading the
copy model's blocks and verdicts. The donor focus (`genome.html`)
leads with the donor's match list (tree links, placement, verdicts;
filters in the column heads), draws the listed matches' segments under
the copies, and paints blocks, dissents and counts where the copy
model applies (the proband and full siblings); the painting PNGs
stay until it also draws segment ends and crossovers, and the
showcase has no genome page yet (its nav links one). Open, in order:
ancestor focus as templates (a code's interval sets per donor and
copy, `intervals.IntervalSet`) with a link from the
family page; match and locus focus, folding in `match_view`'s browser
and `locus_view`; a match scored against the templates (holes where
the ancestor's DNA lies, siblings' absence within complete panels;
`copy_model.match_branches` on real data); matches grouped by which
donors share a stretch (a group focus); later, writing placement assertions, which waits on
how the views get their data.

### Other perspectives

Proposed 2026-11-23: pages reusing the lenses on new kinds of focus,
ordered by what they give for the effort.

- **Farm history** (a place below the parish): who lived there, as
  household lifelines over time from stays and events; the farm's names
  and splits as met; the volumes that cover it. Mostly a timeline lens
  over a people selection by where they lived.
- **The work list** (the tree): what needs doing, person by person,
  nearest the proband first: events without a source, dates against a
  cited record, errata waiting upstream, empty parent slots, implausible
  ages (a mother over 50 or under 15, a child after a parent's death, a
  life past 105), gaps between stays (`residences.py`), loose ends (focus selection),
  places the
  gazetteer cannot resolve. Mostly existing checks gathered on one page.
- **Coverage** (a lineage code, the proband by default): per generation,
  the ancestors known, sourced in an original record, placed on a farm,
  and seen in DNA (blocks, placed matches); a fan chart coloured by it.
  Shows where the next search pays.
- **One-name study** (a surname with its variants): every bearer, grouped
  into the tree's connected lines, each with its earliest known ancestor
  and home parish, so lines not yet joined stand side by side.
- **Who could test** (an ancestor or code): descendants presumed living,
  nearest first, with the expected cM to the donors and any kit;
  recruitment (section 4) and the sister test (section 3) need it.
  Private by nature.
- **Occupations** (moved from "Earlier ideas"): `sel=person:occupation@snickare`,
  titles normalised and dated as places are.
- **Family statistics** (later, for enjoyment): age at marriage, at first
  child, at death, child mortality, by decade and branch; a group against
  the whole tree.

### Shared by the views

- Back and forward as undo, the same in every view: a change to what
  is looked at (focus, a filter) adds a history step; a change to how
  (pan, zoom, folds, open facet groups) replaces it, kept in the
  address. Today Geography and Archives replace on every filter change
  and the family page keeps folds out of the address. Also a link from
  Geography's person facet to carry on with that person in the family
  lens.
- References in one order everywhere, computed, never stored: by
  span (first, then last year), then archive name, then series in
  the archive schema's order (records.md), lowest precedence.
- **Fading** (proposed 2026-11-13; "fog of war" without the fog):
  what lies off the focus's own dimension, such as an in-law's family,
  shown only partly and lighter, so a layout can spread the tree over
  time and space without drawing all of it. The same weight could
  carry certainty (vague dates, unsourced events, the older records
  where names blur into spellings and possible confusions); whether
  one fade can honestly say both is open.
- Errata as the to-do list for the master tree: an applied erratum is
  a fix still waiting in MyHeritage, and it retires itself on the next
  export, so no editing interface is needed. Open: facts about a union
  (a divorce, a marriage date) have no key yet, and the lens neither
  marks a person with open errata nor lists what waits upstream.
- Hand edits from the command line (`tree_store.py` subcommands; man
  pages for every hand-run tool in docs/man/, index intro(1)): additions in the store, corrections in errata.
  Open: people and families have no edit command
  ([#1](https://github.com/UncleCJ/synthetic_genealogy/issues/1)); citations
  that lose their event on a re-import are only logged
  ([#3](https://github.com/UncleCJ/synthetic_genealogy/issues/3)).
- Architecture pictures for packaging the views (say as an iPad
  app): one diagram per question (data, views, what runs where), none
  yet beyond the layer sketch in architecture.md.
- Family and Archives searches fold Swedish spelling variants
  (`viewkit.name_fold` / `FOLD_JS`). Later: a place search could also
  list matching people (linked to the family page, or to their
  places); left out for now to avoid clutter.
- How the views get their data, to consider closely before the lenses
  multiply (for now each view embeds its own, concepts.md): one data
  file or store export shared by the views, a backend over the store
  (lenses that write assertions need one), or the views melded into
  one page. Each changes the deployment contexts in data.md, so it is
  decided, with its assumptions, before it is built. Archives' data
  repeats parish and volume strings on every row (it gzips about 25
  times smaller).
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

### Next, by effort

Easy, a session each:

1. Done 2026-11-23: the nav bar carries the focus. Open: the missing
   Family → Genome links per person with linked matches.
2. Done 2026-11-23: people rules on Geography (`sel=`/`mark=`).
3. Back and forward as undo in Geography and Archives.
4. Place precision as dot or ring; marriages drawn once.
5. The work list as a table page from existing outputs: started
   2026-11-23 with the loose ends, the errata, age checks, empty parent
   slots and stay gaps (`worklist.html`). Open: events without a source,
   dates against a cited record, unresolved places (the roadmap's work
   list entry under "Other perspectives").

Architecture, before the lenses multiply:

1. The link builder in `viewkit.py` (the helper itself moved out of
   `geoview.py` on 2026-11-23).
2. How the views get their data, decided with the rule parser as its
   first test: a shared people table (ids, names, years, parents,
   partners, codes, places) loaded by every page, page data beside it.
3. One rule parser (Python, its JS twin, `store_query.py select`) and
   the derived kinds (steps, loose ends) as rebuilt tables, tested on
   synthetic data.
4. The records tools as pipeline steps (section 1, item 4), so the views
   are rebuilt with the store.

For genealogists:

1. Farm history, then the place card.
2. Coverage and who could test: the next search and the next kit.
3. Done 2026-11-23: steps over a distance and loose ends on the map,
   loose ends with the volumes that would close them, ranked by a
   citation of the person or their household there.
4. The one-name study.
5. Where to look (section 8) as a column in the work list.

## 3. The contested paternity

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

## 4. Data

Run the readers on the remaining archived exports; check chip overlap for
the raw kits; recruit donors on each line the use case needs; a rerunnable
manifest of the cloud archive (type, date, size, which reader).

## 5. Model gaps

Sex-specific genetic maps; endogamy; an exploratory per-copy match-space
view (Jaccard on cM intervals, pile-ups masked). The interval engine, the
X chromosome, pile-up masking and the vendor observation model are in
section 1.

## 6. The second case

Linnea's unknown father, with the same tools and its own config
(`FAMILY_CONFIG`). Open:

- **Raw kits beyond a sibling set** (since 2026-11-14): this family has
  raw kits for the proband and a maternal grandparent, while `[raw_kits]`
  only describes children plus their mother, so the raw kits sit unused
  and phasing fails. Adapt the scheme to describe raw kits per person by
  their lineage path from the proband (as `[[placement.relatives]]`
  already does). The first use is to split the proband's maternal copy
  into MM and MF by where she does or does not share with the
  grandparent.
  The genome page breaks the same way: it treats every subject with
  copy-model blocks as a donor whose codes run from the proband, so a
  grandparent donor (who *is* MM) and a person with only passive matches
  (seen in others' lists, no segments of their own) are painted as if
  they were the proband. Wanted: donors chosen by their path from the
  proband (codes shifted, or the donor left out with the reason), and a
  page that says what is missing when nothing applies.
- **Sides from tree-linked matches** (since 2026-11-14): placement gives
  a segment its parent side only from a mother's match list or from a
  relative sharing it (`[[placement.relatives]]`). Tree links reach the
  copy model, which then picks the grandparent on a known side, but they
  never set the side themselves. In a family without a mother export,
  every kit the relatives don't cover stays unsided, and those they do
  cover come out on their path alone (here, MM only on FTDNA). Let a
  segment shared with a tree-linked match, or the copy model where it is
  sure, give the side.

## 7. Places as dated assertions

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
  image. Riksarkivet's terms are published (records Public Domain Mark,
  metadata CC0, open APIs for material over 110 years, rate limits, IP
  logging; docs/records.md): bulk use is a question of capacity and
  goodwill, not rights. Next: write to RA before anything beyond the
  citations (pre-1916 church books only, one paced proxy, results back as
  CC0 PAGE or ALTO XML, bulk transfer instead of crawling); their own HTR
  list (2025-10-22) covers court, police and commission archives, no
  parish archives. Until then, fetch per citation.
  Started by hand (2026-11-14): `data/cache/iiif/volumes.tsv` (private for
  now) maps image → pages → years, rote or farm for the volumes read while
  checking one line, with the fetched images cached beside it. Lessons:
  pastorates bind several parishes' series in one volume; MyHeritage's
  household "Sida" differs from Riksarkivet's page labels (the viewer's
  own labels match); farm order within a rote holds between rounds; tiled
  header strips find a year or farm cheaply. Next: make the file public
  (structure only), read it in `volumes` instead of guessing, and pace
  image reading (each read costs tokens).
  Death and burial books (sketch, tried on 11 cached
  pages): Apple Vision finds lines and reads header years, not names;
  Riksarkivet's open handwriting model (TrOCR, run locally) reads the
  name column cut along the form's rules and split at ink valleys: the
  right name on 9 of 12 known entries, the age beside it on 6. Free-form
  ledgers (no columns) fail. Matching must take name and age together (a
  namesake on the same page scored higher once). Next: match against
  every tree death in the parish and year. The readers (`htr.py`,
  `cells.py`) are in `experiments/register_ocr`; the scoring stays private.
  The cited people's rows (rows(1), 2026-11-23): read from the shelf's
  line files without images, everyone cited on a page placed at once;
  moves and remarks (lyte, frejd, notes; flagged words such as
  sinnessjuk, dömd, fattighjon). Next: the front-matter registers of the
  insane in the församlingsböcker; flagged remarks checked by eye and
  cited.
- A virtual archive shelf: per parish archive, its series and volumes as
  a browsable shelf (years, image count, open or login-only, digitised or
  not), each volume opening on its known structure (the volume layout
  file: image → years, pages, sections) and the tree's citations into it;
  the archives view grows into it. State: shelf(1) keeps cited volumes in
  `data/archive` (manifests with Riksarkivet's structure; cited pages,
  by image or by page through Riksarkivet's label, and index pages full
  size; covers and spines small; thumbnails between; raw Vision and TrOCR
  text; front matter classed; written page numbers in `pages.tsv`);
  serve(1) pages through them and the Archives and Family views link ⌂ to
  held images. Open: the cited person found on the page (name variants,
  birth year) and the matched line kept with the reference; a reference
  that seems broken marked; volumes whose labels run off the written
  pages reported; a shelf view per parish archive; fill on any miss;
  `structure.tsv` into the repo.
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

## 8. Geography of matches

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
ranking, scored by a distance between place distributions such as
Wasserstein) and more than 20 testable matches in the shared-match graph.
Footprint factorisation (NMF over matches) is worth a one-day look only;
reading its components as ancestors is not earned.

Built properly it needs: geographic assertions as assertions (a hand-kept
one, such as a match's own ancestral parish, is weak evidence for placement in turn), footprints as place × fuzzy time
intervals, footprints computed from the store, full-depth lineage paths,
and views (a matches layer in the geography view, a parish-hints column in
prospects, links from `match_view`).

Caveats: parishes as the unit, farms only where precise, at the event's
date (section 7); little resolution if every branch lived in the same few
parishes (experiment 1 says when); soft time windows; matches' own trees
are mostly unavailable. Match-level maps stay private, since matches are
living people.

## 9. Simulation on the actual pedigree

Ped-sim (read by `simulate.from_pedsim` since 2026-11-12) or msprime's
fixed-pedigree mode on the pedigree from the tree store: many simulated genetic outcomes of one known pedigree, with
crossovers placed by a genetic map. It would calibrate today's judgement
calls (the 7 cM floor, the short-block rule, the mother-window rule, the
anchor weights), give the sister test its power and the cM distributions
for a full- versus half-sister likelihood ratio (simulated jointly, since
siblings' totals are not independent), and feed the synthetic test
scenarios. Vendor detection (thresholds, false segments, phasing errors)
must be simulated on top, or the results flatter the method; the vendor
calibration (section 1, order for the genetics) measures it. The
paternity's simulation-based inference starts now, in parallel with the
deep-crossover test (Ped-sim is read; msprime's fixed pedigree next); the
rest after the store becomes the hub. A short tutorial for CJ comes
before any design.

## 10. Agents as scoped tasks

A task is a bounded hypothesis: which parent slots, how many generations,
which sources, what counts as done. Findings come back as assertions
marked agent-sourced, with citations and confidence, into a review queue;
nothing counts until CJ accepts it, and rejections keep their reason. Same
read and write path as everything else. Delivery stays open: reports,
served pages, batch runs and notebooks are renderers over the same
queries. Segments stay typed rows with a shared provenance id, and
aggregates (totals, clusters, triangulation) stay derived.

## 11. Parked

Hypotheses as computed objects (likelihood ratios beside documents; after
simulation); structuring records from images (handwritten-text recognition
of household examinations into proposed stays); ideas from the 2020 gist
not carried forward (match metrics such as SNP density, age as a
constraint, patronymics, causality, ancestry composition, cultural
heritage).

From the review of 2026-11-23: value of information (ranking the next
kit or record by its effect on a likelihood not yet calibrated; after
the paternity's inference); the dyadic coordinate (a rendering of the
copy posteriors, once they are worth looking at); code length as a
reporting unit only; an inheritance-vector or family ARG model, except
for fusing raw genotypes from other branches and reconstructing
ancestors, until relatives' genotypes arrive.

## 12. Earlier ideas, not started

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

