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

**Round 1: foundations**

1. An interval type with bp↔cM genetic-map conversion, for segments,
   crossovers, stays and volume year ranges.
2. Synthetic test scenarios: single donor, donor + parent, half-sibling or
   twin-cousin, three siblings + parent, an unrelated kit.
3. The assertion record, with readers for hand anchors, tree links,
   paintings, shared-match votes, errata, store edits and research entries;
   and an identity module (match keys, tree ids, gazetteer ids, with key
   strength), replacing the name-normalising spread over several modules.
4. Split `family.toml` into donors (kit → tree person, files, vendor, date)
   and hand-kept assertions (anchors, identities, twins, known
   relationships) in `notes/`; drop the child/mother roles, since
   relationships come from the tree; `kits.py` stops grouping by platform
   with a mother slot.
5. The tree store as the hub: steps read and write through it, not loose
   CSVs. Drop picking the painting by file timestamp, and
   `config.ANCHOR_FILES` and the HOME map (steps declare what they write and
   its kind of state).
6. Exports and checks: a lossless DNA Painter round trip (full path codes,
   group = deepest known shared couple, confidence), prospects without the
   mother and with one threshold for every donor, GEDmatch validation for
   any donor pair with a known relationship, and FTDNA ICW lists merged into
   the shared-match graph.

**Round 2: the new core** (design for review: [design-copy-model.md](design-copy-model.md))

7. The copy model, replacing `phasing_labels.label()`, with leave-one-out
   support per block. It does not stop at grandparents: where full-depth
   tree links allow, it carries great-grandparent labels on each copy, and
   adjacent incompatible labels yield ancestral crossover edges (a
   crossover in the deeper ancestor's meiosis). Later, recursive deduction:
   a grandparent's descendants, through their tested descendants, separate
   that grandparent's own two copies (the prerequisite for the copy test in
   item 2). Placement in two halves (side, then grandparent), and
   `revelations` versus `match_placement` settled as runner and library.
8. A pipeline driven by the data available: steps declare needs and
   outputs and skip rather than fail; `--without <person>` runs for
   validation; an explicit fixed-point loop instead of running twice.
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
