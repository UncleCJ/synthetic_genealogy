# Design: the copy model and the store as hub

A proposal for roadmap item 1, steps 5 and 7–9, written before the code so
it can be reviewed. Built so far: the store as hub (`outputs.py`) and a
copy model from lineage claims and their segment ends (`copy_model.py`),
for a single donor and for phased siblings (the phasing's copy labels
enter, not the genotypes themselves). It replaces the current
chain (phasing, then labels, then placement) only once it does at least as
well on the checks listed at the end.

## Why the current chain can't simply be generalised

Today the genetics is a sequence of hard decisions. The HMM decodes three
siblings' inheritance vectors; a tested mother fixes which side is
maternal; anchors vote, block by block, for which grandparent each copy
label means; placement then reads each match segment off that painting.
Each step works because the one before it has already phased the copies.

Without three siblings and a parent, that order falls apart:

1. **A match segment says "one of the two copies", not which.** For an
   unphased donor, a segment with a relative descending from ancestor X
   says that one of the donor's two copies at that locus came from X. It
   is a disjunction. Two overlapping claims for FF and MM fit together
   (one per copy); FF and FM overlapping cannot both be true unless the
   pedigree collapses there. Today's labeller never meets this, because
   the copies are already apart.
2. **Overlapping matches are on the same copy or on opposite copies**, and
   without triangulation (do the matches match each other there?) we can't
   tell which.
3. **Votes are not independent.** The labeller weighs a claim by SNPs x
   weight, so one match counts once per segment, per sibling and per
   vendor, and five tested cousins of one family count five times.
4. **Segment ends carry crossover information, but noisily.** An end is a
   crossover on the donor's own line, a crossover on the match's line, or
   an artefact of detection (SNP spacing, chip differences, vendor error
   tolerance, phase switches in unphased matching).

## The model

**State.** Along each chromosome, for each tester, the hidden state is
the *pair* (lineage of the paternal copy, lineage of the maternal copy),
each a node in the tree of lineage codes down to a chosen depth (three or
four letters to start: great- or great-great-grandparents). With several
siblings the state is the joint inheritance vector, as in today's HMM, and
the lineage labels sit on the parents' copies rather than on each child's.

**Transitions.** Crossovers, placed by the genetic map (sex-specific when
the map has it: a paternal-copy crossover uses the male map). A crossover
belongs to a named meiosis: the one between the tester and a parent
changes the first letter's copy, one in a grandparent's meiosis changes
the third letter, and so on. That is what makes *ancestral crossover
edges* first-class: a change of label at depth k with no change above it
is a crossover in that ancestor's meiosis.

**Evidence, each a factor on the state** (all optional):

| Evidence | Factor |
| --- | --- |
| Genotypes of siblings and a parent | today's HMM emissions |
| Siblings sharing a match segment end to end | same copy there (today's soft IBD evidence) |
| A match segment with a descent claim (match descends via path P) | one of the two copies is under P, with a false-positive rate by cM (short segments are often false) |
| A tested parent's segment with the same match | the tester's copy on that side |
| A segment end | a soft vote for a crossover nearby, with the endpoint spread measured per vendor |
| A hand painting (DNA Painter) | a descent claim like any other; weight by quality, not by source |

**Independence.** Every claim carries a group (assertions.py): one match
counts once, and a family of tested relatives sharing one ancestral couple
counts as roughly one. The first version caps each group's total weight;
a later one could model the correlation.

**Output.** A posterior per stretch of each copy over lineage codes: the
painting becomes a belief with probabilities, not a label. Placement of a
match is then the posterior of its segments' copies. Leave-one-out support
for a block is the posterior computed without that claim.

**Recursive deduction** (later): a grandparent's own two copies are
separated by that grandparent's other descendants, through their tested
descendants. In the model this is the same state one level up. It is the
prerequisite for the contested-paternity copy test.

## Calibrating the noise from our own data

- **Endpoint spread** per vendor: from the pairs where two siblings share
  the same match segment end to end (thousands of pairs), and from the
  same match exported by both FTDNA and MyHeritage.
- **False-segment rate by cM**: from segments with a documented relative
  that fall where the painting says the relative cannot be, and from the
  simulator (simulate.py).
- **Which genetic map the vendors use**: checked 2026-11: MyHeritage's cM
  follow HapMap II GRCh37 exactly (median ratio 1.001, IQR 1.00–1.00);
  FTDNA's are close (median 1.02, IQR 1.00–1.06). So the map can compute
  cM for any stretch consistently with the vendors, e.g. for the
  containment rule, which today spreads a segment's cM over its bp.

## The store as hub

`tree_store` today keeps one current value per thing, and nothing in the
genetics reads it. The proposal:

- **Hand-kept state stays in files** (`notes/assertions.toml`, errata,
  `tree_edits.json`): readable, diffable, backed up. The store is never
  the only copy of anything kept by hand.
- **The store gets an `assertion` table**, rebuilt each run from every
  source (assertions.read), and the genetics steps read claims, segments
  and the painting from the store instead of from CSVs. CSVs remain as
  views for reading, written from the store.
- **Steps declare what they read and write**, and of which kind of state,
  replacing `config.ANCHOR_FILES` and the HOME map. That also lets the
  pipeline skip a step whose inputs are missing, and run `--without
  <person>` for validation.

## Order of work, and how to avoid regressions

1. Keep the current chain as the reference; build the copy model beside
   it, writing to its own outputs.
2. Test on the simulator first: with three siblings and a parent it must
   recover the truth as well as the current chain; with a single donor it
   must not claim more certainty than it has (calibration: of the blocks
   it calls at 0.9, about 90% right).
3. On real data, compare with the current chain on: agreement with the
   mother (99.8–100%), GEDmatch (93.2% of bp), held-out sibling
   consistency (97.1%), tree links landing on their predicted grandparent
   (210 of 238 for one sibling). Switch the default only when it matches
   or beats all four.

## Decisions for CJ

1. ~~Genetic map~~: decided, HapMap II GRCh37 (averaged), in the phasing
   since 2026-11-10.
2. **Store**: an `assertion` table rebuilt each run, with hand-kept claims
   staying in files (proposed), or the store as the place where hand-kept
   claims are edited.
3. **Depth to start with**: three letters (great-grandparents) or four.
