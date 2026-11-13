# How the genetics work

The ideas and the reasoning behind the genetic half: what each model
assumes, why its rules are as they are, and what the checks have shown.
Terms: [concepts.md](concepts.md). Modules: [architecture.md](architecture.md).
What runs and what it prints: [pipeline.md](pipeline.md). Numbers below come
from the simulator or from one family's data (three phased siblings and a
donor mother) as of November 2026.

## The problem

The first chain was a sequence of hard decisions: an HMM decodes three
siblings' inheritance vectors, a donor mother fixes which side is
maternal, anchors vote for which grandparent each copy label means, and
placement reads each match segment off that painting. Each step works
because the one before has already phased the copies. Without three
siblings and a parent the order falls apart:

1. **A match segment says "one of the two copies", not which.** For an
   unphased donor, a segment with a relative descending from X says one of
   the donor's copies there came from X: a disjunction. FF and MM assertions
   overlapping fit (one per copy); FF and FM cannot both be true unless the
   pedigree collapses there.
2. **Overlapping matches are on the same copy or on opposite copies**, and
   without triangulation we cannot tell which.
3. **Votes are not independent.** One match appears once per segment, per
   sibling and per vendor, and five donor cousins of one family are one
   family.
4. **Segment ends carry crossover information, but noisily.** An end is a
   crossover on the donor's line, one on the match's line, or an artefact
   of detection (SNP spacing, chip differences, vendor tolerance, phase
   switches in unphased matching).

The answer is *phasing as belief, not a step*: the copy model below, a
fuzzy belief per stretch of each copy about which ancestor it came from,
sharpened by whatever evidence exists. The painting chain still runs beside
it as the reference.

## Phasing

At every position each sibling carries one of the father's two copies and
one of the mother's, and those copies are the grandparents' DNA, so "which
copy" means "which grandparent". Manual visual phasing compares sibling
pairs (fully, half and not identical regions) and reasons that a crossover
in sibling X changes both comparisons involving X and leaves the third.
That reasoning is a hidden Markov model over inheritance vectors (the
Lander–Green algorithm), so `visual_phasing.py` lets Viterbi do the
bookkeeping. For three siblings the state has 16 values relative to
sibling 1: whether sibling 2, and sibling 3, carries the other copy of side
A, and the same for side B. A donor mother's genotypes enter the
emissions, and segments two siblings share end to end with a match are
soft evidence that they carry the same copy there.

The sides are A/B, not paternal/maternal: from siblings alone the parents
are indistinguishable on autosomes, and A/B can even swap partway along a
chromosome where the siblings' states on both sides are alike. The 0/1
grandparent labels are just as arbitrary. `phasing_labels.py` anchors them
with two kinds of outside evidence:

1. **A parent's kit.** Her genotype must equal the sum of the two
   reconstructed alleles on her side. A rolling vote says which side is
   maternal; maximal runs with the same answer are blocks, inside which the
   0/1 labels are consistent.
2. **Lineage assertions** (documented relatives and tree links; DNA Painter
   paintings only when `[phasing] anchors` lists them). A segment claimed
   "MF…" on a sibling says that sibling's maternal copy there is the
   mother's father's; inside a block every such assertion votes for what the
   label means. A hand anchor weighs 10, a confirmed identity 3, a plain
   name join 1 (unique tree person, at least 20 cM). Dissenting assertions are
   reported, judged leave-one-out, not dropped.

A documented relative becomes a lineage assertion by a rule per segment
(`documented_anchors.py`): a child with a full match list who shares the
relative's segment carries that grandparent there; one who lacks it
(segments of `MIN_CM` and up, so detection is not in doubt) carries the
other. Without the mother's kit, a long segment one sibling shares and
another lacks puts the second on the other grandparent. A relative related
to both of the mother's parents breaks the rule; the share is then unusually
high for the documented relationship. Matches whose path ends at a
grandparent couple are skipped.

GEDmatch's one-to-one comparisons (`gedmatch_io.py`) are an independent
check: its own fully, half and not identical calls on the same raw data.
Disagreement is expected at segment ends and below its 7 cM floor.

The painting this gives names each copy by one vote per chromosome and
block; the copy model below reads the same labels as soft evidence instead.

## Placement

Placing a match segment means naming its parent's side, then its
grandparent.

**The side, for a child's segment** (`match_placement.py`):

- The mother has the same match on an overlapping segment: maternal.
- The match is absent from the mother's list: paternal, since what the
  child got from her she carries too. Only for segments of at least
  `ABSENCE_MIN_CM` (10 cM; below it false segments are common, and absent
  because they aren't real), and only for matches first seen, in any
  accession of any donor on the platform (an `earlier` export, FTDNA's
  match date), on or before her list's date; a newer match is simply
  missing. Paternal by absence is still weaker than maternal by overlap.
- The mother matches them, but the segment reaches `EXCESS_CM` or more
  beyond her segments with them: paternal (containment: she carries all of
  the child's maternal DNA). Only for exports of one vintage.
- The mother matches them elsewhere: open. Then the phased siblings decide
  where they can (`sides_from_siblings`): a real segment of 10 cM or more is
  shared by exactly the siblings carrying the same copy of that parent, so
  which siblings share it names the side. The outcome rates are learnt from
  the segments the mother's list decides; held out, it is right
  98.6–98.9%.
- The mother's AutoCluster window (every match she shares 35–400 cM with)
  counts as a current list for child totals of about 105–200 cM, three
  times its floor: at a lower threshold a maternal match of 69 cM turned out
  missing from her run.
- Without a donor mother or phased siblings, relatives at a known path
  (`[[placement.relatives]]`: a half-sibling, a grandparent) name the side,
  and the grandparent where the path names one, of the segments they share
  with the match. Their absence counts for nothing yet; for close
  relatives with a complete export it should (Sparse regimes, below).

**The mother's own segments** (her copies are MF and MM) are voted by every
child on the same platform: a child sharing it puts it on the copy the
child got there; a long segment (`OTHER_COPY_CM`) the child lacks, where the
child's maternal copy is one grandparent throughout, is on the other copy
(long, because a match list needs about 20 cM in total). Children voting
differently is a conflict.

**The grandparent** comes from the donor's copy model where there is one
(placed when at least 0.9 sure over the segment), with the painting's
reading kept beside it as the check (`painting_grandparent`). A segment
straddling the donor's own crossover is flagged: a false segment, or a
misplaced crossover.

**Sibling consistency** (`sibling_consistency.py`): siblings sharing a
segment with one match, on one side, with nearly the same ends, carry the
same copy there. Short painted blocks (under 1,500 SNPs) that at least two
such pairs outvote and none support are relabelled; each correction names
the painting it was made for, by checksum.

## The copy model

**State.** For one donor, the paternal and the maternal copy are
modelled apart (an assertion's lineage code says which copy it concerns). Each
copy's state is its lineage code at a chosen depth: depth 3 gives four
states per copy (FFF FFM FMF FMM for the paternal one).

**Transitions.** Along the chromosome, letter j of the code changes where
the meiosis of the ancestor at level j − 1 had a crossover (probability
from the genetic map, Haldane). When letter j changes, the deeper letters
refer to another person's genome and are drawn afresh. A change at depth k
with no change above it is an *ancestral breakpoint*. One
sex-averaged map for all meioses so far.

**Evidence**, each a factor on the state, all optional:

| Evidence | Factor |
| --- | --- |
| A match segment with a descent assertion (via path c) | copy c[0] is under c throughout, unless the assertion is wrong |
| A segment end | a soft vote for a crossover nearby, on our side's meioses |
| Phased siblings' copy labels | all siblings' assertions name one shared state per parent |
| A hand painting (DNA Painter) | a descent assertion like any other, weighted by quality, not source |

An assertion's weight w is the chance it is right: the link's confidence times
the chance a segment of that length is real (short vendor segments are
often false). It enters as (1 − w) + w·[state under c] over the segment,
tempered so the whole segment counts as one observation; overlapping
segments of one match are merged. Every assertion carries an independence
group (`assertions.py`), so one match counts once.

A segment end is, with probability ½ (half the meioses that can cut a
shared segment are on our side) times the assertion's weight, a crossover on
our copy, spread over our side's meioses. On the simulator this made
conflicts a more reliable sign of a false segment (81% false, from 64%) at
the price of fewer confident calls.

**Phased siblings** (`SiblingCopyModel`). The phasing's copy labels let
every sibling's assertions name one belief per parent copy. On the simulator
this takes confident grandparent calls from 15% of the genome to 94%
(right 99.8%). Unlike the painting, which names copies once per chromosome
by majority, it can follow assertions where the phasing's labels flip meaning:
from sibling data alone, two siblings recombining at a spot looks the same
as the third doing so.

**Calibration** (`calibration()`). The posteriors should mean what they
say. The single-donor model loses part of a segment's evidence to the
crossovers it allows inside it, so it counts each segment twice (expected
calibration error 0.10 → 0.06 on the simulator; on real data sure of 33%
of the painted genome instead of 21%, agreeing with the painting there
93%). The sibling model counts each segment once and allows a 0.5% chance
that a phasing label is wrong, which caps its confidence honestly.

**Output.** Forward-backward posteriors per grid point, blocks of the most
likely state, and per assertion a leave-one-out verdict (the posterior that its
copy is under its code, computed without it).

**Where it stands.** On one family the sibling model is sure on 92% of the
painted genome and agrees with the painting there 96.5%. Placement reads it
by default (`[placement] method`): it places 95–97% of the sided cM the
painting places, agrees with it on 99.4% of segments where both decide, and
agrees better with the held-out DNA Painter paintings (91% against 86%) and
with siblings sharing a segment end to end (97.8% against 97.0%). The
differences sit on two maternal stretches where it reads the phasing's
labels the other way round, siding with the documented anchor. The price is
coverage where few relatives speak.

## Sparse regimes

A single donor with no donor parent or siblings, on the simulator
(built-in and Ped-sim, which agree within about 3 points here; 2026-11-12,
not yet on real data). The runs are kept as sketches to learn from and
rerun: `experiments/sparse_branches.py` (branch posteriors, naive against
joint, self-training rounds) and `experiments/close_relatives.py` (the
grandmother and half-sibling regimes).

- **Per-match branch posteriors rank; they do not place.** Position alone
  narrows four grandparents to one candidate per copy, and a match's
  segments at different loci intersect to one branch. With 90% of
  relatives anchored, the truth is in the top two for nearly every
  multi-segment match; at 30%, accuracy is 28–48% (chance 25%) and the
  truth in the top two 52–82%. Single-segment matches stay a pair.
- **Combine a match's segments by joint path probability**, not by
  multiplying per-stretch marginals, since copy states are autocorrelated:
  the evidence ratio Z(anchors + match coded g) / Z(anchors), four forward
  passes per chromosome per match. The gain is modest.
- **A close relative's absence is the strongest cheap lever.** A donor
  maternal grandmother's segments say MM; the gaps between them (shrunk 2
  cM per end, 5 cM and longer, weight 0.95) say MF. Share of the maternal
  copy named at grandparent level, and right when named (6 families):

  | Evidence | Named | Right |
  | --- | --- | --- |
  | 30% of distant relatives anchored | 8% | 98% |
  | + her segments | 51% | 95% |
  | + her absence | 83% | 99.5% |
  | her segments and absence, no tree | 82% | 99.4% |

  Robust to vendor dropout (holes of 3–8 cM in 30% of her segments: still
  98.6%), and it needs no new model: both are ordinary lineage
  assertions. Absence needs a complete export, and pedigree collapse would
  break it (she can share through the other grandparent).
- **A half-sibling relayed through anchors adds little** (8% to 12%): it
  only repeats what the anchors say.

**Staying linear.** State multiplies with depth (2^(d−1) per copy), with
donors modelled jointly, with child lines (×4 each, hence recursive
deduction's cap of 5), with unanchored matches assigned jointly (4^N),
and, worst, with same-or-opposite-copy factors between overlapping
matches (a colouring problem with conflicts). So: exact inference only on
small per-copy chains; matches interact only through those chains, with
one latent per match (not per segment), scored in one pass, and no loops
between matches.

## Deep labels and breakpoints

**Deep labels** (`deep_labels.py`) read the copy model's great-grandparent
letters back in bands: sure (posterior ≥ 0.9, what placement uses), likely
(0.7–0.9) and leaning (the best code, not a call); a block's posterior is
its mean. An assertion names a great-grandparent when its lineage is longer than
two letters; its verdict is the model's leave-one-out reading. How a tree
assertion found its person matters: a confirmed identity, a distinctive surname
(counted as confirmed: the model read against 10% of their segments,
against 28% of patronymic ones), or a patronymic name join (weak: -son
names repeat). On one family the sibling model is sure of a
great-grandparent on 20–140 cM per sibling and likely on 870–1,280 cM. The
evidence is the limit, not the model: every assertion naming a
great-grandparent is a tree link, and every deep assertion the model reads
against already differs at the grandparent (a wrong person, not a wrong
deep letter).

**Breakpoints** (`edges.py`) lists where things change along a chromosome:

- **X**, a sibling's crossover, from the phasing's copy labels.
- **B**, a change of the copy model's most likely code: in the second
  letter a crossover in the sibling's parent's meiosis; in the third letter
  only, an ancestral breakpoint (the grandparent's meiosis).
- **E**, a cluster of segment ends across matches: how many matches and
  donors, their side, grandparent and tree codes, how many segments cover
  the spot (a pile-up has many), and what explains it, if anything.

Ends shared by matches from different branches suggest a crossover on the
donor's own copy; unexplained clusters of several matches sharing one
lineage are candidates for a deeper ancestor's crossover. One-way clusters
are coverage limits (Lessons, below). The tolerance and the "explained"
radius are judgement calls; vendor endpoint noise is about 0.5–1 cM.

## Recursive deduction

An ancestor has one genome; each descendant carries a different, random
part of it, about half less per generation. The natural unit is therefore
the ancestor's genome, with each donor's segments as windows into it. The
sibling model already works this way one level up (three siblings see both
of a parent's copies on about 75% of the genome). Recursive deduction is
the next level: a grandparent G's two copies, P (from her father) and M
(from her mother), reached through her other children's lines. Their union
is G's partly reconstructed virtual genome, the idea behind Borland
Genetics' ancestor reconstruction, and the prerequisite for the
contested-paternity tests ([roadmap](roadmap.md) §2):

- **Copy test:** do matches from the named father's family fall only on P?
- **Sister test:** do her sisters' descendants match on P and M (full
  sisters) or on M only (maternal half-sisters)?

**Structure.** The siblings' copy from G is a mosaic of P and M, switching
at G's crossovers in that meiosis (1–2 per chromosome). So the recursion
needs:

1. **G's crossovers.** Her other children are seen through their donor
   descendants. Where segments from two or more independent child lines end
   at one spot, two-way, with no sibling crossover there, that is G's
   crossover. Lines from one child count as one; an identical twin of the
   father is the father's own meiosis.
2. **A flip at each crossover**, as the phasing's copy labels flip at a
   sibling crossover, so one name per chromosome names every stretch.
3. **Names from the uncontested side only.** M is named by assertions through
   G's mother; P is "the other copy". Assertions through the contested father
   and the sister lines are held out as groups: they *are* the tests, so
   using them as evidence would be circular.

What must not count: segments under 10 cM, one-way end clusters, pile-ups,
matches placed by the side rule alone; each match counts once.

**On the simulator** (placement on G's copy from the truth, so this
measures the recursion alone): with first-cousin child lines, 49% (2
lines) to 83–87% (9) of G's visible crossovers are found; a spot seen by
one line is a true breakpoint about 30% of the time, by two 70–90%, by three or
more 97–100%. Naming, not breakpoint finding, is the bottleneck: P is named only
across confident breakpoints. The copy test, read with each relative left out
and a permutation p-value, gains power mainly from relatives through G's
mother:

| through G's mother | families with p < 0.05 (of 10) | mean difference |
| --- | --- | --- |
| 2 | 0 | 0.05 |
| 4 | 3 | 0.16 |
| 8 | 8 | 0.28 |

The sister test, one second-cousin line per sister, reads right in 7–8 of
10 families; it needs more sister lines. Not modelled: placement errors,
false segments of 10 cM and up, pile-ups, a female map.

**A joint per-line model** (`posterior_joint`, an option): one chain per
chromosome over which copy of G the siblings carry, whether each child line
carries the same one, and whether a donor in the line still holds it;
absence counts where a sibling with data carries G's copy. It calls fewer
but far cleaner crossovers (precision 0.63–0.82 against 0.45) and leaves
the copy test as it was. It keeps at most 5 lines, since the state doubles
twice per line.

**On real data.** The three uncontested grandparents check the method:
with mother-side anchors alone the test reads the right way on all three
(p 0.19, 0.009, < 0.002; the weakest has pedigree collapse), and held-out
relatives land on their own side 84–100%. Two of the three have no child
lines, so this validates that relatives through one parent cluster on one
copy, not the breakpoint finding. On the contested grandparent the test cannot be
read yet (two relatives through her mother, p 0.41; the simulator says
about 8 are needed). The cheapest gains, in order: link each donor first
cousin to their parent among G's children; check the name joins in the
small lines; find donors through G's mother (`--others` lists the
unexplained matches on G's copy by the copy they sit on).

## Shared matches

A shared-match link says both matches share DNA with the donor and
with each other. Usually that is one ancestral line, but pile-ups,
endogamy and double relationships make links across lines too, so a link
is weak, symmetric evidence.

**Observability** (`match_graph.py`). AutoCluster runs differ in
thresholds: each includes only matches in its donor's cM window and
reports shared matches above its own minimum. A missing link means "not
shared" only if both matches were in that run, otherwise "not looked at".
So each pair carries `observable` (runs that included both) and `reported`
(runs that report the pair), and support = reported / observable. A link
seen in every run that could see it is strong; one observable in three runs
and reported in none is evidence against. Built without any segment data,
the graph falls into the four grandparents' neighbourhoods the segments
give independently (assortativity 0.59 on one family).

**Votes** (`icw_phasing.py`):

1. Validation: for matches the segments place confidently, how often do
   their confidently placed shared matches vote the same grandparent?
2. Candidates: an unplaced match gets its neighbours' vote if at least
   `MIN_VOTES` vote and `MIN_SHARE` agree. The vote settles the side; the
   match's own segments read on that side pick the grandparent, or the
   couple when both carry DNA. Written as low-weight assertions.
3. Conflicts: pairs placed confidently on different parents' sides, each a
   pile-up, a double relationship, a placement or a phasing error.
   Matches descending from a grandparent couple vote for the side only.
4. Deeper lineage: tree-linked matches hand their deeper code to shared
   matches on the same grandparent: a candidate, not a finding.

**Prospects** (`prospects.py`) are close matches the tree doesn't explain:
at least `MIN_CM` with any donor (roughly second to third cousins), not in
the GEDCOM by full name (weak both ways: namesakes, spellings). Shared
matches that are in the tree, with their lineage codes, are the branch
hint.

## Relationships

`relationship_check.py` compares, for each confirmed identity, the cM the
tree expects (2 × kinship × 6800 cM, kinship over all paths, identical
twins as one person) with the cM observed per donor. An identity can sit
`down` generations below the tree person, so a line not in the tree still
gives an expectation. A ratio far from 1 says the tree misses a path (often
through a parent whose ancestry isn't traced) or has a wrong one; a ratio
near 2 with all DNA on one grandparent is the typical missing path. Single
values vary a lot (a second cousin ranges about 0.2–2.5 × the average), so
read all donors together.

Odds per relationship, as in DNA Painter's WATO, come from simulated
distributions (`simulate.relationship_cm`: vendor-style detection on a flat
map, no interference, no population IBD), with equal priors over the
candidates. Unvalidated, and too narrow for distant cousins (roadmap §1,
sharpeners).

## Simulation

`simulate.py` drops DNA through a known pedigree and keeps the truth.
Founders carry unique copies; everyone else gets one copy from each parent
by a meiosis with Poisson crossovers in cM (no interference), converted to
bp through a genetic map (sex-specific maps optional). Identical twins
share one genome. True IBD is every stretch where a copy of each person
descends from the same founder copy. Vendor detection goes on top: a cM
threshold, noisy ends and false short segments, so inference is tested
against realistic flaws, not perfect truth. Pieces are joined where only a
deeper founder's copy changes, which no vendor can see (left unjoined, they
made false all-line breakpoints in recursive deduction).

Not modelled: genotypes (the phasing tests make their own), pile-ups and
population IBD, chip differences, X. Chromosome lengths are rough.

For sex-specific maps and crossover interference, `simulate.py` also reads
[Ped-sim](https://github.com/williamslab/ped-sim) (external, GPL; nothing
bundled): `pedsim_def` writes our pedigree as a def file and `from_pedsim`
reads its output back under our names, so detection and the models run
unchanged. Ped-sim's `h0` is the paternal haplotype. It needs Boost's math
headers, the Bhérer refined map converted as in its README, and the
Campbell interference file; cite Caballero 2019, Bhérer 2017 and Campbell
2015 if results are published. It matters for sex-specific questions and
for a genotype-level rung (msprime founders, a real IBD detector), roadmap
§8.

## Calibrating from our own data

- **Endpoint spread** per vendor: from siblings sharing one match segment
  end to end, and from matches exported by both FTDNA and MyHeritage.
- **False-segment rate by cM**: from documented relatives' segments that
  fall where the painting says they cannot be, and from the simulator.
- **Genetic map:** MyHeritage's cM follow HapMap II GRCh37 exactly (median
  ratio 1.001); FTDNA's are close (median 1.02). So the map computes cM for
  any stretch consistently with the vendors.

## Lessons

- **Confidence must be measured, not assumed.** Each knob should name the
  check behind it: `calibration()` on the simulator, held-out checks on
  real data (painting, DNA Painter, sibling pairs, the other vendor).
- **The weak link is often the "truth" used to check.** Sides from a
  match's absence in the mother's list include false segments: against
  them sibling evidence looked 82% right, against the overlap rule 98.7%.
  Use the strongest rule as reference; read disagreement with a weak one as
  a lead.
- **Segments under about 10 cM carry little side or breakpoint information**
  (sibling sides at 7–10 cM right only 64–82%; false segments end at
  random). Breakpoint work starts at 10 cM.
- **Ends running one way are coverage limits, not crossovers.** A crossover
  on a shared copy makes segments both end and start there; clusters of
  only ends or only starts sit where chip SNPs run out (centromeres, tips).
  A cluster mixing both sides' matches cannot be one copy's crossover.
- **Copy labels can be right while their names are wrong** (the two-or-one
  siblings recombining case above).
- **Never promote model-placed matches to anchors automatically.** In
  self-training rounds the newly confident calls were right 0–43% of the
  time. The safe loop: the model suggests, the genealogist confirms with
  records, then it anchors.
- **Calibration does not transfer between regimes.** At 30% anchors,
  counting a segment twice made beliefs of 0.75 right 0.53 of the time;
  counting once was honest but rarely sure. Calibrate per regime.
- **The 10 cM floor holds for anchors too.** With 7 cM, anchors' false
  7–10 cM segments planted spurious beliefs (confident calls about 60%
  right).
- **Feedback loops settle quickly.** Sides from siblings feed the next
  phasing run as shared-segment evidence; a second pass changed nothing.

## Open questions

- Recursive deduction: name the copies from the uncontested side only, with
  the contested side and sister lines held out as the tests (current), or
  from all assertions, reading the tests leave-one-group-out.
- Whether great-grandparent changes in the copy model coincide with
  unexplained two-way end clusters on one grandparent, which would make
  ancestral breakpoints checkable; and how often a match's tree path is
  right at full depth.
- Depth 4 (great-great-grandparents), once deep assertions exist.
