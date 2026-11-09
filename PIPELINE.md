# Pipeline: what runs, in what order, and what it prints

This is an anonymised walkthrough of the tools in this repository, run on
one family: three full siblings (A, B, C) with raw data, their tested
mother (M), segment exports from FTDNA and MyHeritage, DNA Painter backups,
a GEDCOM tree and Genetic Affairs AutoCluster runs. Names, kit IDs and
segment positions are left out; the counts and rates are from a real run
(November 2026).

```bash
python3 pipeline.py              # every step below, in order
python3 pipeline.py placement    # from one step onward
python3 pipeline.py --only icw   # a single step
```

Each run appends to `data/pipeline_log.md` (private: it names matches):
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
research     ok              0 s  check research entries, write research/INDEX.md
```

Everything family-specific comes from `family.toml` (format in
`family.example.toml`). Outputs go to `data/`.

## 1. painter: `dnapainter_io.py`

Reads DNA Painter profile backups. A group named "MF Erik Example / Anna
Example" says: segments painted here came through the mother's father, whose
parents were Erik and Anna. Each painted segment becomes an assertion with
its lineage code. Output: `assertions_dnapainter.csv`.

```
kind       close_family  lineage  unplaced
A                    77      327         0
B                     0      219       112
C                     0      183       156
side conflicts: 0
```

## 2. anchors: `documented_anchors.py`

Relatives with a documented tree path (`[[anchors]]`) become heavy
assertions. With the mother's kit, a maternal anchor is judged against her
segments; without a father's kit, a paternal anchor is judged among the
siblings (a long shared segment gets the anchor's grandparent; a sibling
lacking it where another has it gets the other one). Output:
`assertions_documented.csv`.

```
subject  lineage  rule
A        FF       child shares it                          14
         FM       child lacks it (a sibling shares it)     13
         MF       child shares it                          14
         MM       child lacks it                           16
...
```

## 3. phasing: `phasing_labels.py` (runs `visual_phasing.py`)

An inheritance-vector HMM over the three siblings' raw genotypes (16
states: which grandparental copy each sibling carries relative to the
first). The mother's genotypes are part of the model, so one side is
hers. Segments two siblings share end to end with a match are soft
evidence that they carry the same copy there. Viterbi gives the path;
anchors and paintings name the copies. Output:
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

For each sibling's segment: which parent (the mother shares an
overlapping segment with that match → maternal; the match is missing from
her list, which is no older than the child's → paternal), then which
grandparent, from the painting. Rules for newer exports: an `earlier`
export of the same kit keeps absence valid for matches already in it; the
mother's AutoCluster window (every match she shares 35–400 cM with) counts
as a current list for child totals of about 105–200 cM (3 × its floor).
On matches already decided by segments the window was right 21/21
(maternal) and 22/22 (paternal) at ≥ 60 cM, but a maternal match of 69 cM
was later found missing from the mother's run (the run seems not to list
every match in its window), hence the higher threshold. Output: `placed_segments.csv`, `placed_matches.csv`,
`revelations.md`.

## 5. consistency: `sibling_consistency.py`

If two siblings share a segment with the same match, on the same parent's
side, with nearly the same ends, they carry the same grandparent copy
there. The check counts how often the painting agrees, and relabels short
blocks (< 1,500 SNPs) that at least two such pairs outvote and none
support. Output: `sibling_consistency.csv`, `phasing_corrections.csv`,
`phasing_grandparent_segments_corrected.csv` (used by placement while newer
than the painting).

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
Affairs node/edge files and FTDNA ICW lists. Per tester: how often the
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
tester, importable next to hand-made ones) and a PNG per tester: phased
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
thresholds from distorting the statistics: a missing edge counts against a
pair only where both ends were in view. A bipartite tester → match layer
holds each tester's cM. Node attributes: placement pooled over siblings
(grandparent, or side for couple-level matches), tree lineage code, cM
per tester. Output: `match_graph.gexf` (for Gephi), `match_graph.png`,
`match_graph_strong.png` (edges seen in every run that could see them),
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
Cross-side edges concentrate on a few matches (one has 10), worth checking
for a double relationship or a misplaced small segment.

## 8c. prospects: `prospects.py`

A research shortlist: matches sharing ≥ 60 cM with a sibling (roughly
second to third cousins: common ancestors three to four generations back)
or ≥ 90 cM with the mother, that are not in the GEDCOM. A strict full-name
join and a looser one (a given name plus the surname, doubled letters
normalised) separate "not in the tree" from "probably in it under another
name". Each row: cM per tester (from segments, else the AutoCluster run),
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

## 9. gedmatch: `gedmatch_io.py`

Validation against an independent algorithm: saved GEDmatch one-to-one
comparisons (all shared segments, and fully identical regions only) per
sibling pair, against the model's pairwise state, weighted by base pairs.

```
bp agreement with GEDmatch NIR/HIR/FIR: 93.2%      (91.6% before the re-decode)
  (A, B): 94.3%   rows GEDmatch NIR/HIR/FIR, columns model, Mb:
                  [[592, 47, 7], [68, 1340, 27], [0, 9, 700]]
```

Fully identical regions agree almost entirely; most of the rest is edge
placement and short shared stretches below GEDmatch's 7 cM floor.

## 10. research: `research_log.py`

Checks the research entries (TOML headers) and writes `research/INDEX.md`.

```bash
python3 research_log.py new hypothesis "Erik Example is Anna's father"
python3 research_log.py at 9 120000000    # entries with a segment there
```

## Tools used by hand

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
not pipeline steps yet. Outputs go to `data/`, except the gazetteer,
which is public geography and lives in `gazetteer/`.

```bash
python3 places.py                 # archive codes in the tree's citations -> Wikidata parishes
python3 places.py name "Ryr"      # candidate parishes for a name
python3 places.py history Q...    # one parish's splits, merges and codes over time
python3 riksarkivet.py "SE/VALA/00472/A II a/3"   # one volume: years, content note, viewer link
python3 volumes.py                # citations -> volumes, pages, farms; volumes.html, volume_refs.csv
python3 volumes.py farm Example   # one farm across volumes, as text
python3 gazetteer.py build        # add places from citations; variant proposals to data/gazetteer_todo.md
python3 gazetteer.py show Example # look up a place or parish
python3 residences.py             # stays, gaps and bracketed moves -> data/residences.csv
```

- `textfix.py` repairs damaged å/ä/ö in every reader (decomposed letters,
  spacing marks, mojibake), so one parish does not split into two.
- `places.py` resolves a place by Riksarkivet archive code first (exact:
  Wikidata P5324), then by a vendor's volume label, then by name (only
  candidates: names repeat and are abbreviated).
- `volumes.py` reduces every citation to parish, series/volume
  (`A II a/3`), page and farm, with a tidiness tier, and classes each
  cited person against the proband (ancestor, relative by branch, spouse
  of a relative, unlinked). It applies `errata.py` on the way: corrections
  kept beside the master export in a private `data/errata.toml`, each
  reported as applied, retired (fixed upstream), conflict or orphan.
- `gazetteer.py build` only adds and fills, so hand edits survive; clear
  spelling variants within a parish merge automatically, the rest become
  proposals to review.
- `residences.py` turns volume citations into stays, lists gaps with the
  next volume to open, and brackets moves between parishes by volume
  years.

On one tree: all 34 parish archive codes in the citations resolve to a
Wikidata item; 791 people have volume citations, with 273 bracketed moves,
376 gaps and 59 stays not yet collated as residence events. These tools
are sketches, written against one Gramps export of a MyHeritage tree.

## What a run on new data needs

- New segment exports: list them in `[[segment_exports]]`; mark one-to-many
  selections `partial`; give a newer export its `earlier` one.
- New AutoCluster runs: add `[[icw]]` entries; for the mother, also a
  `[[mother_window]]`.
- Then `python3 pipeline.py`. On a first run with new data, run it twice:
  the phasing uses the shared segments the previous placement found.
