# Lenses and pages

A design doc (2026-11-14). The model below names what exists; of the
genome lens, the donor focus is built (`genomeview.py`), the rest is a
design on paper. State and next steps are in the
[roadmap](roadmap.md), terms in the [glossary](concepts.md#glossary).

## The model

- **Focus:** what is looked at. A person; a group (a branch by lineage
  code, a household, a list); a comparison set of two to five; a match; a
  locus (an interval on one chromosome); a place; a volume. Proposed: any
  of these as a selection by rule, also of derived kinds (a person's
  steps between places, the loose ends of their paths), and a rule that
  marks instead of selecting (roadmap, "Focus selection"). The focus
  lives in the address, so every state can be linked.
- **Lens:** one shape over one focus. The shapes: tree (pedigree,
  descendants), timeline (lifelines, stays), map, segments (chromosomes),
  table or documents (events, references, volumes). A lens never calls
  another lens.
- **Page:** lenses sharing one focus. Composition happens here, not inside
  a lens, so a lens can appear on several pages.
- **Overlay:** a value from another domain drawn on a lens's marks with
  the shared encodings (lineage colour, fading for uncertainty, ticks for
  instants). Keyed by person id or lineage code, so a tree lens can carry
  DNA or places without becoming a DNA or map lens. A dated base map
  (`maplayers.py`) is not one: it lies under the map lens's marks, keyed
  by place and year, not drawn on them.
- **Links** between pages are context links or plain links (glossary).

The lineage code is the key that joins DNA and the tree: the copy model's
blocks, placed matches and the family page's ancestors all carry one, and
`lineage.py` gives each code its colour.

The pages today, read through the model:

| Page | Focus | Lenses on it |
| --- | --- | --- |
| Family (`familyview.py`) | person | tree (pedigree, descendants), timeline (household lifelines), tables (events, references) |
| Geography (`geoview.py`) | group, by facets | map |
| Archives (`volumes.py`) | place, volume, person | documents |
| Match report (`match_view.py`) | match | segments, tables (paths, ancestors, references) |
| Locus (`locus_view.py`) | locus | segments |
| Genome (`genomeview.py`) | donor | tables (matches, segments, counts), segments |

The family page's lenses are not yet separable; the tree lens is pulled
out when a second page needs it (a group focus, or a tree with an
overlay), not before.

## Design on paper: the genome lens

One segments lens; the painting made interactive, and the place where the
copy model's findings are seen.

**Focus kinds.**

- *Donor:* 22 chromosomes, two copies each, blocks in lineage colours.
- *Ancestor* (a lineage code): where that ancestor's DNA lies in every
  donor, siblings stacked so their crossovers line up; the matches placed
  under the code beside it. New: nothing shows this today.
- *Match:* its shared segments against the donor's blocks (today the
  browser in `match_view`).
- *Locus:* everyone sharing at one interval, with the pile-up check (today
  `locus_view`).

**Draws.** Position along the chromosome is the axis (in cM, bp on
hover). A block is a bar in its code's colour, faded by posterior; segment
ends and siblings' crossovers are ticks; a donor or copy with no data is
blank, not grey. Depth is a control: grandparents (level 2) or
great-grandparents (level 3), a deeper code drawn inside its parent's hue.

**Counts first.** Per donor and code, the share of the genome placed
against the expected (a grandparent about a quarter); per ancestor, the
cM found across donors and the matches placed under the code.

**Interactions.**

- Hover a block: code, ancestor's name, posterior, model, the assertions
  that support it and their leave-one-out verdicts.
- Click a block: that ancestor becomes the focus; a context link opens
  the family page on them.
- Brush a stretch: that locus becomes the focus.
- A list of disagreements: assertions whose verdict goes against them,
  and stretches where the models or the painting disagree. For the DNA
  what errata are for the tree: the work to do.

**Reads** (all rebuilt state):

| What | From |
| --- | --- |
| blocks | `copy_model_blocks.csv`: chrom, side, cM and bp span, lineage, posterior, subject, level, model |
| crossovers | `phasing_crossovers.csv` |
| verdicts | `copy_model_verdicts.csv` |
| placed matches and segments | `copy_model_placed_matches.csv`, `copy_model_placed_segments.csv` |
| code → person, names | the store, codes computed as `familyview.lineage_codes` does |

**Writes.** Nothing at first. Later a descent assertion confirming or
rejecting a placement, which needs the decision on how views get their
data (roadmap): a static page cannot write.

**Questions for the store and the models.**

- Blocks exist at levels 2 and 3 only; deeper codes wait on deep labels.
- Single-donor and sibling models both write blocks; the lens shows the
  one placement reads (`[placement] method`) and marks where they differ.
- Pedigree collapse gives one ancestor several codes; the ancestor focus
  takes the union.
- Partial MyHeritage panels: absence of a match there means little, so
  coverage is drawn per platform.
- The X chromosome has no model yet; it is drawn as absent.
- Size: blocks and crossovers are small enough to embed; placed segments
  (tens of thousands of rows) are loaded per focus or summarised.

**Steps.** Donor focus (built 2026-11-14: blocks, fade, dissents,
counts; no segment ends or crossovers drawn yet; since 2026-11-15 led by
the donor's match list, whose listed or selected matches' segments are
drawn under the copies, so it serves donors the model cannot paint);
then the ancestor focus and an "in the genome" link from
the family page; then match and locus as focus kinds, folding in
`match_view`'s browser and `locus_view`.
