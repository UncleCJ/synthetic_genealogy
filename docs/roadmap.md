# Roadmap

What comes next, roughly in order. Terms are explained in
[concepts.md](concepts.md); the current modules in
[architecture.md](architecture.md).

## 1. One coherent codebase

The unifying idea is already written down: the three kinds of state
(received, kept by hand, rebuilt). Every module should read received or
hand-kept state and write only rebuilt state. The guiding concept for the
genetics is **phasing as belief, not a step**: each tester has a copy
model, a fuzzy belief per stretch of each copy about which ancestor it came
from. It starts near blank, works with a single donor, and is sharpened by
whatever evidence exists. Evidence is assertions of one shape (subject,
claim, interval, source, asserted_by, weight, date); tree links and DNA
Painter paintings have equal standing, weight follows evidence quality, and
one match counts once however many sources name it. Lineage paths are kept
at full depth, not truncated to two letters.

**Round 1: foundations** (state as of 2026-11-10)

1. Done: an interval type with bp↔cM genetic-map conversion
   (`intervals.py`), and the phasing on a real map (HapMap II GRCh37, the
   map MyHeritage's cM follow). Not yet used for stays and volume year
   ranges beyond the shared year parser.
2. Done: synthetic test scenarios (`simulate.py`): single donor, donor +
   parent, twin-cousin, three siblings + parent, an unrelated kit.
3. Done: the assertion record (`assertions.py`) for hand anchors, tree
   links, paintings and shared-match votes, and an identity module
   (`identity.py`, `lineage.py`) in place of the name-normalising spread
   over several modules. Still to read into it: errata, store edits,
   research entries.
4. Done: hand-kept claims (anchors, identities, twins) apart from the
   setup, in `data/notes/assertions.toml`. Moved to round 2, beside the
   copy model: dropping the child/mother roles and the platform grouping
   with a mother slot in `kits.py`, since placement is built on them.
5. Done: the genetics steps read and write their tables through the store
   (`outputs.py`, with an `assertion` table); painting corrections name the
   painting they were made for, instead of a file timestamp;
   `config.ANCHOR_FILES` replaced by `assertions.ANCHOR_SOURCES`. The store
   records which step wrote each table; steps declaring what they need, so
   the pipeline can skip rather than fail, is item 8. The HOME map stays:
   it is the declaration of which files are hand-kept, store or cache.
6. Done: prospects without the mother, with one threshold for every
   tester. Waiting for the copy model, since they need its beliefs:
   confidence in the DNA Painter round trip, and GEDmatch validation for
   any donor pair. Not started: FTDNA ICW lists in the shared-match graph
   (FTDNA keys are names, so joining them with MyHeritage needs care).

**Round 2: the new core** (design for review: [design-copy-model.md](design-copy-model.md))

7. The copy model, replacing `phasing_labels.label()`, with leave-one-out
   support per block. Started 2026-11-10 (`copy_model.py`): a single donor,
   one HMM per copy at depth 3, lineage claims as soft evidence, tested on
   simulated families (confident grandparent calls right 92-99% of the
   time). On real data, from each sibling's own claims alone: sure on about
   36% of the painted genome, agreeing with the painting there 90-92%; its
   conflicts overlap the labeller's. Segment ends as soft crossover votes
   added the same day: conflicts become a more reliable sign of a false
   segment (simulated: 81% false, from 64%); on real data agreement with
   the painting rises 2-3 points, documented anchors have no conflicts,
   and where both decide the copy model and the labeller agree on 93% of
   claims. Phased siblings added the same day (SiblingCopyModel: one
   shared belief per parent, named by every sibling's claims): on one
   family it is sure on 92% of the painted genome and agrees with the
   painting there 96.5%. Most of the rest is one spot (chr1, maternal,
   ~154 Mb) where the documented anchor and the tree links all say the
   phasing's labels flip meaning: two siblings recombining there, not the
   third as the HMM chose. Calibrated the same day (`calibration()`): the
   single-donor model counts each segment twice, since it loses part of a
   segment's evidence to the crossovers it allows inside it (simulated
   calibration error 0.10 to 0.06; on real data sure on 33% of the painted
   genome instead of 21%, agreeing there 93%); the sibling model counts
   each segment once and allows for wrong phasing labels (0.5%). Where
   siblings are phased, read the sibling model's verdicts: the single
   model's newly decisive ones include a few false conflicts with
   documented relatives. Placement through the copy model added the same
   day (`copy_model.place`, the side still from the mother's list, the
   grandparent where the model is at least 0.9 sure): on simulated
   families every held-out relative's segment it places is right; on real
   data it places 95-97% of the sided cM the painting places, agrees with
   it on 99.4% of segments where both decide, agrees better with the
   held-out DNA Painter paintings (91% against 86%) and with siblings
   sharing a segment end to end (97.8% against 97.0%). The differences sit
   almost all on two maternal stretches (chr1 below ~154 Mb, chr15 ~90
   Mb), where it reads the phasing's labels the other way round. Switched
   the same day: placement reads the copy model by default (`[placement]
   method`, "painting" to go back), the painting's reading kept beside it
   (`painting_grandparent`). Downstream every check holds or improves
   (siblings placing a match on the same grandparent up 0.2-1.2 points per
   pair; DNA Painter 91% from 86%; matches spread over several
   grandparents 97 from 123); the price is coverage where few relatives
   speak (the mother's placed segments 76,000 cM from 88,000: chr3, chr22,
   the starts of chr8, 17 and 19), where the painting names a copy by one
   vote per chromosome. The side from the siblings added 2026-11-11
   (`match_placement.sides_from_siblings`): where the mother's list gives
   no side, the phasing's copy labels say which siblings carry the same
   copy of each parent, and which of them share the segment with the
   match names the side (outcome rates learnt from the segments the
   mother's list decides; 10 cM and up). Held out, it is right 98.6-98.9%
   where the mother shares the segment; on one family it gives 1,723 more
   segments a side and places 1,570 more matches, and all 69 new sides
   that the other vendor's export also decides agree with it. It does not stop at grandparents: where full-depth
   tree links allow, it carries great-grandparent labels on each copy, and
   adjacent incompatible labels yield ancestral crossover edges (a
   crossover in the deeper ancestor's meiosis). Later, recursive deduction:
   a grandparent's descendants, through their tested descendants, separate
   that grandparent's own two copies (the prerequisite for the copy test in
   item 2). Requirements and a first version on the
   simulator 2026-11-11 (`grandparent_copies.py`): her crossovers are
   found from her other descendants' segment ends (68-87% with 4-9
   first-cousin lines), and with 8 or more relatives through her mother
   the copy test reads right in 8-10 of 10 simulated families; naming her
   father's copy, not finding edges, is the weak part. Placement in two halves (side, then grandparent), and
   `revelations` versus `match_placement` settled as runner and library.
8. A pipeline driven by the data available: steps declare needs and
   outputs and skip rather than fail; `--without <person>` runs for
   validation; an explicit fixed-point loop instead of running twice.
   Meanwhile, a family without raw kits (single testers, half-siblings, a
   tested grandparent) has to run the steps one by one with `--only` to
   get past the first failure; the records steps and the copy model run,
   placement and everything after it stop on the missing painting. Two
   stopgaps would cover that until the needs are declared: a
   `--keep-going` flag (run every step, list the failed ones at the end),
   and placement reading the copy model alone when there is no painting.
9. Sharpeners: the HMM for any n ≥ 2 siblings with an optional parent; a
   twin-cousin or half-sibling kit; sibling consistency as "same copy"
   links instead of a painting editor; a relatedness check that flags kits
   whose sharing doesn't fit their stated relationship.

**Round 3: the rest**

10. Pile-up masking in placement; the X chromosome model; the records
    tools (`volumes`, `gazetteer build`, `residences`) as pipeline steps; a
    shared view helper for the HTML views; output descriptions in `serve.py`
    supplied by the writing step; the showcase check through the identity
    module.

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
2. Phase one generation up: her children, represented by their tested
   descendants, separate her two original copies.
3. The sister test: acknowledged sisters' descendants matching on both of
   her copies means full sisters; on one copy only, maternal half-sisters.
4. Check the match from the named man's family against a prediction: its
   segments must fall on her paternal copy, in exactly the cousins who
   carry that copy there.
5. Write it up: a likelihood ratio for full versus half sisters from the
   second-cousin amounts (siblings' totals are not independent), a
   hypothesis page weighing DNA and letters, and a calibration of how many
   testers make it decisive (Ped-sim or msprime on the actual pedigree).

## 3. Data

Run the readers on the remaining archived exports; check chip overlap for
the raw kits; recruit testers on each line the use case needs; a rerunnable
manifest of the cloud archive (type, date, size, which reader).

## 4. Model gaps

Sex-specific genetic maps; endogamy; an exploratory per-copy match-space
view (Jaccard on cM intervals, pile-ups masked). The interval engine, the
X chromosome and pile-up masking are in item 1.

## 5. The second case

Linnea's unknown father, with the same tools and its own config
(`FAMILY_CONFIG`).

## 6. Places as dated assertions

- Resolve by archive code (exact), then volume label, then name (names are
  ambiguous: "Ryr" is four parishes).
- **Parishes, congregations and towns as separate entities** (decision in
  concepts.md): harvest all Wikidata items per cited archive code, with
  dates, dated codes and successions (archives with more than one item are
  the Gränna-like cases); tag cached volumes by the congregation their notes
  name; split Gränna and review the odd keys (town names, regiment and
  castle congregations, the dated key); a resolver that returns candidates
  narrowed by date, volume and farm, else the archive. Cross-check with
  Skatteverket's "Sveriges församlingar genom tiderna".
- Missing historical aliases on Wikidata; county and diocese at an event's
  date; TORA for farms.
- One place parser (started 2026-11-10): whole place strings now split
  (`plac_parts`, moves read as their destination) and resolve
  (`explain_plac`) in the gazetteer, which `places_rules` traces directly.
  Still two parish rules: `volumes.normalise` (parishes from the
  citations, `PLAC_SUFFIX`) and `Gazetteer.parish_rule` (the gazetteer's
  parishes, `PARISH_SUFFIX`); join them once the gazetteer is built as a
  pipeline step, so every family's parishes are in it before the views run.
- Review the gazetteer proposals; apply person-level errata in `gedcom_io`;
  collate stays and open the gap volumes `residences.py` lists.
- Reading errors: the long s (ſ) read as f, as p, or beyond recognition
  (-hult names suffer most). Candidate checks, unvalidated: f→s before
  s/h/t giving an existing name in the parish; an edit-distance search
  against TORA or OSM names in the parish; a parish lookup that falls back
  to `ortho()` on a unique hit. Old f for v (Kalf-, Hof-) stays a hand
  rename, since a general rule would break names like Rolf.

## 7. Geography of matches

Next to explore. Joining the two halves a second way: every lineage path has a footprint
(the dated places of its ancestors), so any DNA claim that names a path
inherits one. Matches, clusters and prospects would then point to parishes,
decades and the volumes to open; a parish would show which matches point to
it; and a match whose segments say one branch while its shared matches point
to another branch's parishes is worth opening. First a throwaway experiment
over existing outputs: do the branches differ geographically per period,
and in a hold-out test, do shared matches alone rank the real ancestral
parish in the top 3 or 5? Only a usable hit rate makes it a pipeline step.
Match-level maps stay private, since matches are living people.

## 8. Simulation on the actual pedigree

Ped-sim or msprime's fixed-pedigree mode on the pedigree from the tree
store: many simulated genetic outcomes of one known pedigree, with
crossovers placed by a genetic map. It would calibrate today's judgement
calls (the 7 cM floor, the short-block rule, the mother-window rule, the
anchor weights), give the sister test its power and the cM distributions
for a full- versus half-sister likelihood ratio (simulated jointly, since
siblings' totals are not independent), and feed the synthetic test
scenarios. Vendor detection (thresholds, false segments, phasing errors)
must be simulated on top, or the results flatter the method. After the
store becomes the hub; start with a short tutorial for CJ before any design.

## 9. Parked

Hypotheses as computed objects (likelihood ratios beside documents; after
simulation); structuring records from images (handwritten-text recognition
of household examinations into proposed stays); ideas from the 2020 gist
not carried forward (match metrics such as SNP density, age as a
constraint, patronymics, causality, ancestry composition, cultural
heritage).

## 10. Earlier ideas, not started

Verify the unverified export formats with real samples; a triage and group
interface; an existing tool as a host for the inference engine instead of a
new application; Gramps or Wikibase as the store of record.
