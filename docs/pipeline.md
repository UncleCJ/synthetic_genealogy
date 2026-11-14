# Pipeline: what runs, in what order, and what it prints

This is an anonymised walkthrough of the tools in this repository, run on
one family: three full siblings (A, B, C) with raw data, their donor
mother (M), segment lists from FTDNA and MyHeritage, DNA Painter backups,
a GEDCOM tree and Genetic Affairs AutoCluster runs. Names, kit IDs and
segment positions are left out; the counts and rates are from a real run
(November 2026).

```bash
python3 pipeline.py              # every step below, in order
python3 pipeline.py placement    # from one step onward
python3 pipeline.py --only icw   # a single step
python3 pipeline.py --keep-going # don't stop at a failed step; list them at the end
```

Setup: `pip install -r requirements.txt` (python ≥ 3.11). The first step,
`tests`, runs smoke tests on synthetic data (`python3 -m unittest discover -s
tests`, under a second): the GEDCOM reader and its vendor quirks, kinship
with twins, the tree store's round trip and edits, the AutoCluster reader,
sibling pairs, and the phasing model on simulated siblings. A failure stops
the run before any output is overwritten.

Each run appends to `data/output/pipeline_log.md`, with one file per run in
`data/output/logs/` (private: they name matches):
per step the command, the time it took and its summary lines. A full run
takes about four minutes.

The steps below are the genetic chain. The records tools (tree, places,
record volumes, residences) run by hand for now; they are listed under
[Records: tools run by hand](#records-tools-run-by-hand).

```
painter      ok              1 s  DNA Painter backups -> lineage assertions
anchors      ok              2 s  documented relatives -> weighted anchor assertions
phasing      ok             30 s  raw kits + mother -> inheritance HMM -> grandparent painting
placement    ok             56 s  segment exports -> parent and grandparent per segment and match
consistency  ok             13 s  segments siblings share vs the painting; short-block corrections
placement2   ok             58 s  placement again, on the corrected painting
icw          ok              3 s  shared-match graphs vs the placement; candidates
export       ok              8 s  painting -> DNA Painter backups and PNGs
graph        ok              6 s  merged shared-match graph with observability -> GEXF, PNGs
prospects    ok              8 s  close matches not in the tree, with side and branch hints
gedmatch     ok             29 s  model vs GEDmatch one-to-one FIR/HIR (validation)
research     ok              0 s  check research entries, write notes/research/INDEX.md
```

Everything family-specific comes from `family.toml` (format in
`examples/family.example.toml`). Outputs go to `data/output/`.

## 1. painter: `dnapainter_io.py`

Reads DNA Painter profile backups. A group named "MF Erik Example / Anna
Example" says: segments painted here came through the mother's father, whose
parents were Erik and Anna. Each painted segment becomes an assertion with
its lineage code. Output: `assertions_dnapainter.csv`.

By default these paintings do not name the grandparents in the phasing
(step 3); they are a held-out check, compared with the placement in step 4.
Listing `"dnapainter"` under `[phasing] anchors` in `family.toml` makes them
anchors again. Hand-painting clusters in DNA Painter is slow, and a
painting that also anchors the phasing cannot check it.

```
kind       close_family  lineage  unplaced
A                    77      327         0
B                     0      219       112
C                     0      183       156
side conflicts: 0
```

## 2. anchors: `documented_anchors.py`

Relatives with a documented tree path (`[[anchors]]`) become heavy
lineage assertions (`assertions_documented.csv`); the same rule runs over
the tree's matches (`assertions_tree.csv`), as weighted votes, not
verdicts. The rule and the weights: [genetics.md](genetics.md#phasing).

```
subject  lineage  rule
A        FF       child shares it                          14
         FM       child lacks it (a sibling shares it)     13
         MF       child shares it                          14
         MM       child lacks it                           16
...
```

## 3. phasing: `phasing_labels.py` (runs `visual_phasing.py`)

The inheritance-vector HMM over the three siblings' raw genotypes, with
the mother's genotypes in the model; the anchors name the copies
(`[phasing] anchors`: documented and tree by default), each judged
leave-one-out ([genetics.md](genetics.md#phasing)). Output:
`phasing_grandparent_segments.csv`, `phasing_crossovers.csv`,
`phasing_verdicts.csv`, `phasing_grandparents.png`.

```
shared-segment evidence: 282 intervals
chrom  informative  mother_agreement  side_swaps
1             1476          1.000000           0
14            1520          0.999342           0      (91.9% before the mother entered the model)
15            1603          1.000000           0
...                                                   (≥ 0.9976 on every chromosome)
verdict
agrees       488
conflicts     82                                       (106 before)
```

190 crossovers for three children (about 205 expected).

## 4. placement: `revelations.py` (uses `kits.py`, `match_placement.py`)

For each sibling's and the mother's segment: which parent's side (the
mother's list, then the phased siblings, then the mother's AutoCluster
window), then which grandparent (the copy model, the painting's reading
kept beside it; `[placement] method = "painting"` uses the painting alone).
The rules and why: [genetics.md](genetics.md#placement). Output:
`placed_segments.csv`, `placed_matches.csv`, `revelations.md`.

## 5. consistency: `sibling_consistency.py`

Siblings sharing a segment with one match on one side carry the same copy
there; the check counts how often the painting agrees and relabels short
blocks the pairs outvote ([genetics.md](genetics.md#placement)). Output:
`sibling_consistency.csv`, `phasing_corrections.csv` and, for reading,
`phasing_grandparent_segments_corrected.csv`.

```
4373 sibling pairs sharing a segment end to end; 4219 consistent, 154 disagree
chrom  parent
15     M         40      (one region shared by 8+ matches with all three
2      F         33       siblings and the mother: likely pile-ups)
...
2 short blocks corrected
```

Before the mother entered the model: 4,057 consistent; on held-out pairs
93.8% → 97.1%.

## 6. placement2

Placement again, on the corrected painting.

## 7. icw: `icw_phasing.py` (uses `icw_io.py`)

Shared-match ("in common with") graphs from AutoCluster CSVs, Genetic
Affairs node/edge files and FTDNA ICW lists. Per donor: how often the
shared matches' vote names the same grandparent as the segments
(validation); candidate placements for unplaced matches (the vote gives the
side, the match's own segments read on that side give the grandparent, or
the couple when both carry DNA); pairs placed on opposite parents' sides;
cluster composition; deeper-lineage hints from tree-linked shared matches.
Matches descending from a grandparent couple are labelled by side (pooled
over siblings). Output: `icw_report.md`, `assertions_icw.csv`.

```
## B, MyHeritage: 193 matches, 870 shared-match pairs
- Validation: ... 27 of 27 matches (100%) ...
- Candidates for unplaced matches: 53. No call: 57.
## A, FTDNA: 321 matches, 652 shared-match pairs
- Validation: ... 30 of 38 matches (79%) ...      (after dropping one Genetic
                                                    Affairs edge code that mostly
                                                    joined opposite sides)
## M, MyHeritage: 108 matches, 326 shared-match pairs
- Validation: ... 13 of 13 matches (100%) ...
```

## 8. export: `dnapainter_export.py`

The computed painting back as DNA Painter backups (one new profile per
donor, importable next to hand-made ones) and a PNG per donor: phased
grandparent copies pale, placed match segments ≥ 12 cM on top, tree-linked
matches in the group of the deepest ancestor the tree gives. Group names
follow the lineage-code convention, so an edited backup reads back in
through step 1.

```
A: 2870 segments -> dnapainter_phased_A.txt, painting_A.png
...
```

## 8b. graph: `match_graph.py`

All MyHeritage AutoCluster runs (siblings and mother, 2023 and 2026) merged
into one graph keyed by MyHeritage match ID, with **observability**: for
each pair, the runs in which both matches were inside the run's window
(`observable`) and the runs reporting them as sharing (`reported`);
`support` = reported / observable. That keeps runs with different
thresholds from distorting the statistics: a missing link counts against a
pair only where both matches were in view. A bipartite donor → match layer
holds each donor's cM. Node attributes: placement pooled over siblings
(grandparent, or side for couple-level matches), tree lineage code, cM
per donor. Output: `match_graph.gexf` (for Gephi), `match_graph.png`,
`match_graph_strong.png` (links seen in every run that could see them),
`match_graph_cross_side.csv`.

```
run A    175 matches in window 35-400 cM,  304 pairs   (2023)
run A    138 matches in window 40-400 cM,  553 pairs   (2026)
run M    192 matches in window 35-400 cM,  326 pairs   (2026)
...
matches: 689
shared-match edges: 1601
edges seen in every run that could see them: 585
edges seen in only some runs that could see them: 262
edges between placed matches: 268
... same grandparent: 198
... same parent's side: 221
... same grandparent expected by chance: 71
assortativity by grandparent: 0.59
47 cross-side edges
```

The shared-match graph, built without any segment data, falls into the
four grandparents' neighbourhoods that the segments give independently.
Cross-side links concentrate on a few matches (one has 10), worth checking
for a double relationship or a misplaced small segment.

## 8c. prospects: `prospects.py`

A research shortlist: matches sharing ≥ 60 cM with a sibling (roughly
second to third cousins: common ancestors three to four generations back)
or ≥ 90 cM with the mother, that are not in the GEDCOM. A strict full-name
join and a looser one (a given name plus the surname, doubled letters
normalised) separate "not in the tree" from "probably in it under another
name". Each row: cM per donor (from segments, else the AutoCluster run),
side and grandparent (segments, else the shared-match candidate), placed
shared matches, shared matches that are in the tree with their lineage
codes (the branch hint), a rough relationship, the match's own tree size
and link. Output: `prospects.md`, `prospects.csv`.

```
54 close matches not in the tree, 8 probably in it under another name
match     A    B    C    M    side     shared matches in the tree          guess
X1      251  154  153    -    F (ICW)  [FMFF] ...                          2C / 2C1R
X2      125   82  213    -    FF       [FFF] [FFF] [FFF]                   2C / 2C1R
X3      100  109  178  162    MF (ICW)                                     2C / 2C1R
...
```

## 8d. relatives: `relationship_check.py`

For matches confirmed as a tree person (`[[identity]]` in `data/notes/assertions.toml`:
match name, tree ID, who confirmed it, when), the expected shared DNA from
the tree (2 × kinship × 6800 cM, kinship over all paths, so cousin or
uncle–niece marriages count; identical twins from `[[mz_twins]]` count as
one person) against the observed total per donor. Confirmed identities
also replace name guessing in the other tree steps. Output:
`relationship_check.md`.

```
match   tree person            A exp  A obs  B exp  B obs  C exp  C obs  ratio
X1      1C1R via F couple        425    519    425    318    425    246   0.85
X2      2C via FM couple         212      -    212    288    212    250   1.27
X3      "1C", fathers MZ twins  1700   2155   1700   1758   1700   1461   1.05
X4      2C1R, double via F       159    308    159    211    159    411   1.94
```

A ratio near 2 with all DNA on one grandparent says the tree is missing a
path, e.g. through a parent whose own ancestry isn't traced.

## 8e. store: `tree_store.py`

One SQLite file (`data/tree.sqlite`) holding the family tree and the
genetics with equal standing:

- **family tree**: people, families and children (with pedigree type),
  events, sources and citations, imported from GEDCOM; everything not
  modelled is kept verbatim and written back;
- **genetics**: kits (each a tree person), DNA matches (vendor identity,
  optionally linked to a tree person with who confirmed it), totals per
  donor, segments with parent and grandparent, and the phased painting,
  imported from the pipeline's outputs and AutoCluster runs.

Every row has an `origin` (`import:<label>` or `edit:<who>`); every import
and edit is one readable line in `data/store/tree_notes.md`. Re-importing a newer
export replaces imported rows and keeps edited ones. The pipeline's `tree`
step (`import-tree`) does this for the GEDCOM `family.toml` names: the tree
rows are cleared, so people who left the tree go too, and the edits are
replayed from `tree_edits.json`; the genetics and places steps then re-link. Exports: GEDCOM (with
a "DNA match" fact and cM per donor on each linked person) and CSVs of the
genetics tables.

```bash
python3 tree_store.py import data/tree.ged "MyHeritage export 2026-11-09"
python3 tree_store.py import-tree        # the GEDCOM family.toml names
python3 tree_store.py import-genetics "pipeline 2026-11-09"
python3 tree_store.py export data/tree_export.ged
python3 tree_store.py export-genetics data/genetics_export
python3 tree_store.py notes
```

Round trip on a 3,170-person MyHeritage export: no person, name, birth or
death date or parent link changes; 99.7% of GEDCOM nodes come back (the
rest are 51 exact duplicate citations, written once).

```
- 2026-11-09 14:50 · Claude: DNA match MyHeritage:D-… -> tree person MH:I… — tree person has
  married name …; the researcher confirmed the line; cM fit 2C1R
- 2026-11-09 14:50 · Claude: MH:I…: added EVEN Contact with birth family BEF 17 MAR 1953 … —
  the letter opens with thanks for her letter
```

## 9. gedmatch: `gedmatch_io.py`

Validation against an independent algorithm: saved GEDmatch one-to-one
comparisons (all shared segments, and fully identical regions only) per
sibling pair, against the model's pairwise state, weighted by base pairs.

```
bp agreement with GEDmatch NIR/HIR/FIR: 93.2%      (91.6% before the re-decode)
  (A, B): 94.3%   rows GEDmatch NIR/HIR/FIR, columns model, Mb:
                  [[592, 47, 7], [68, 1340, 27], [0, 9, 700]]
```

Fully identical regions agree almost entirely; most of the rest is end
placement and short shared stretches below GEDmatch's 7 cM floor.

## 10. research: `research_log.py`

Checks the research entries (TOML headers) and writes `notes/research/INDEX.md`.

```bash
python3 research_log.py new hypothesis "Erik Example is Anna's father"
python3 research_log.py at 9 120000000    # entries with a segment there
```

## Tools used by hand

`locus_view.py` shows one place on one chromosome: who in the family
shares DNA there, with whom, on which copy, with the siblings' painting,
sibling-shared segments outlined, shared-match links between matches at
the locus (overlap + link = triangulation) and a pile-up check (segments
covering the locus against each donor's genome median per Mb):

```bash
python3 locus_view.py --at 2:237.5 --window 16
```

```
827 segments, 4 links, density B 188/48.0, A 143/45.0, C 143/52.0, M 65/29.0
```

(×3–4 the median: a pile-up; a segment there is weak evidence.)

`match_view.py` writes a match-centred chromosome browser and research
report as one self-contained HTML file (no network; private, in `data/`):

```bash
python3 match_view.py --entry q-some-question                 # focus = the entry's people
python3 match_view.py --entry q-some-question --focus "Erik Example" --out data/report.html
```

Per sibling, both parental copies painted by grandparent; the focus
matches' segments on their copy (dashed on both copies, with each reading's
grandparent, when the side is unknown); other matches on the same stretch
(triangulation candidates, coloured by placement); totals per donor,
shared matches from the merged AutoCluster graph with support, linked
tree persons and the research entry's text. Click a chromosome to enlarge
it, hover for details.


`gedcom_io.py` reads the tree:

```bash
python3 gedcom_io.py summary              # people, families, adopted/foster links
python3 gedcom_io.py find "Example"       # people, with lineage codes from the proband
python3 gedcom_io.py descendants @I0042@ 4
python3 gedcom_io.py rel @I0001@ @I0042@  # closest shared ancestors, as lineage codes
python3 gedcom_io.py matches              # tree people named like DNA matches
```

```
$ python3 gedcom_io.py rel @I0001@ @I0042@
Erik Example (1830–1900): FMFF from @I0001@, 4 generations above @I0042@
Anna Example (1832–1895): FMFM from @I0001@, 4 generations above @I0042@
```

(a third cousin through the father's mother's father's parents.)

## Records: tools run by hand

These read the GEDCOM's citations and places rather than DNA. They are
not pipeline steps yet. Outputs go to `data/output/`, except the gazetteer,
which is public geography and lives in `gazetteer/`.

```bash
python3 places.py                 # archive codes in the tree's citations -> Wikidata parishes
python3 places.py name "Ryr"      # candidate parishes for a name
python3 places.py history Q...    # one parish's splits, merges and codes over time
python3 riksarkivet.py "SE/VALA/00472/A II a/3"   # one volume: years, note, page span, viewer and catalogue links
python3 volumes.py                # citations -> volumes, pages, farms; archives.html, volume_refs.csv
python3 volumes.py farm Example   # one farm across volumes, as text
python3 gazetteer.py build        # add places from citations; variant proposals to data/gazetteer_todo.md
python3 gazetteer.py show Example # look up a place or parish
python3 residences.py             # stays, gaps and bracketed moves -> data/residences.csv
```

How they read places, references and residences:
[records.md](records.md).

On one tree: all 34 parish archive codes in the citations resolve to a
Wikidata item; 791 people have volume citations, with 273 bracketed moves,
376 gaps and 59 stays not yet collated as residence events. These tools
are sketches, written against one Gramps export of a MyHeritage tree.

## What a run on new data needs

- New segment lists: list them in `[[segment_exports]]`; mark one-to-many
  files `partial` (and `same_selection` on the mother's, if the same
  matches were looked up for her); give a newer segment list its
  `earlier` one. How donors
  download them: [myheritage-download.md](myheritage-download.md).
- New AutoCluster runs: add `[[icw]]` entries; for the mother, also a
  `[[mother_window]]`.
- Then `python3 pipeline.py`. On a first run with new data, run it twice:
  the phasing uses the shared segments the previous placement found.
