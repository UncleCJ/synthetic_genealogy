# Concepts

The ideas the code is built on, the words used for them, and the decisions
taken along the way. How the code is laid out: [architecture.md](architecture.md).
What comes next: [roadmap.md](roadmap.md).

## Principles

### 1. Three kinds of state

Everything the project touches is one of three kinds, and each kind is
handled differently:

| Kind | Examples | Edited? | Kept where |
| --- | --- | --- | --- |
| **Received** | vendor segment exports and match lists, GEDCOM exports, raw genotype files, AutoCluster runs, DNA Painter backups | never | `data/input/`, and the private cloud archive folders they came from |
| **Kept by hand** | `family.toml`, errata, place map, research entries, the store's edit files (`tree_edits.json`, `tree_notes.md`) | by a person (or a session on their behalf) | `data/notes/`, `data/store/`, `family.toml`; backed up to a private cloud folder |
| **Rebuilt** | placements, paintings, reports, views, logs, `tree.sqlite`, web-service caches | only by code | `data/output/`, `data/cache/`, `data/store/tree.sqlite`; not backed up |

The master data is never edited. A wrong date in the family tree is not
fixed in the tree's export but in an erratum beside it, keyed so that it
survives the next re-export. Every run checks each correction against the
current data and reports it as applied, retired (the master now agrees),
in conflict (the master changed differently) or orphaned (its target is
gone). The folders and how to browse them: [data.md](data.md). Backups and
the public/private split: [privacy-workflow.md](privacy-workflow.md).

### 2. Assertions with provenance

Each statement records what was claimed, by whom, from which source, with
what confidence and when. The tree, chromosome paintings and placements are
views derived from those statements and recomputed when they change; a
contested claim keeps its rivals beside it rather than overwriting them.

This is the core idea of the [Underlay](https://underlay.mit.edu) from
MIT's Knowledge Futures Group: contested or contradictory statements are
stored together with their context and chains of provenance, and
evaluation is left to separate layers. Their own
[short intro](https://notes.knowledgefutures.org/pub/underlay-short-intro)
uses a genealogical example. Wikibase offers the same shape in practice
(statements with qualifiers, references and ranks), and could link private
families to public anchors on Wikidata.

Today this is a direction more than a fact: only the three anchor sources
(documented relatives, tree links, DNA Painter paintings) share one shape
and can be read interchangeably. Shared-match votes, errata, store edits
and research entries each have their own format. One assertion record is
the first item on the [roadmap](roadmap.md).

### 3. Two halves that check each other

The genetic half places each match segment on a grandparent's copy of a
chromosome; the records half places each ancestor in parishes, farms and
archive volumes. A wrong link in the tree puts a segment on the wrong
grandparent; a misread farm name shows up as a jump on the map or a gap in
the volumes; a match joined to the wrong person disagrees with the
painting. Today the only bridge between the halves is the tree links; the
geography of matches (roadmap) would add a second.

### 4. Paths, not people

DNA travels along paths through a pedigree, so the code addresses paths.
A **lineage code** spells a path from the proband: `F` father, `M` mother,
so `MFF` is the mother's father's father. **Ahnentafel numbers** address
the same direct line (father 2n, mother 2n+1). Under pedigree collapse one
person holds several codes and numbers, which is genetically right: each
path carries its own share of DNA. Collateral relatives are addressed by
the ancestral couple plus a downward path ("9 ↓ 2nd child ↓ 1st child").
With several testers, each has its own view of one shared graph.

### 5. Intervals

Chromosome segments and life events are both intervals on a line, with
fuzzy ends. "This segment lies within a great-grandmother's paternal copy"
and "the move falls between two household examinations" are the same kind
of constraint, so one interval engine (Allen's interval algebra with fuzzy
endpoints, plus bp↔cM conversion through a genetic map) should serve both
halves. Not code yet: segment overlap, stay merging and volume bracketing
each reimplement interval logic today.

### 6. Evidence and hypotheses

Competing claims, confidence and conflict detection apply to documents and
DNA alike. A hypothesis is an explicit object ("the man named in the
records was her biological father") that evidence supports or contradicts,
with the reasoning kept. The research log (`research_log.py`,
[schema](../research/README.md)) holds questions, hypotheses, segments of
interest and findings as dated entries that cite computed output rather
than repeat it.

### 7. Consent and privacy

Borrowed raw data, matches' segment lists and living relatives in a shared
graph all need consent that can be withdrawn. Under GDPR, genetic data is a
special category. The code is public; every family-specific file lives on a
private line of history and in a private cloud folder, never on the public
line ([privacy-workflow.md](privacy-workflow.md)). Public screenshots are
pseudonymised (`showcase.py`). Health findings and any forensic use are out
of scope unless each person consents explicitly. Storing consent itself as
an assertion, so that withdrawal is clean, is an intention, not code yet.

## Glossary

- **Proband:** the person the lineage codes and Ahnentafel numbers start
  from (`proband` in `family.toml`).
- **Kit:** one person's test at one vendor; a tester can have several.
- **Snapshot (of an export):** one export per tester, vendor and date.
  Re-imports are diffed against earlier ones. Not to be confused with a
  *data snapshot*, the dated zip `backup.py snapshot` writes for reading
  elsewhere.
- **Inheritance vector:** for n siblings, which grandparental copy each
  carries relative to sibling 1, giving 4^(n−1) states (16 for three). A
  Lander–Green HMM decodes it along each chromosome with Viterbi.
- **Crossover attribution:** if both relative bits on one side flip,
  sibling 1 recombined; if one bit flips, sibling 2 or 3 did.
- **Side A/B, copy 0/1:** unanchored labels. Siblings alone cannot tell
  paternal from maternal, or grandfather from grandmother, which leaves 8
  labellings per chromosome. Known relatives resolve them ("anchoring").
- **Tested parent:** sorts matches by side directly. In raw-data phasing it
  makes that side near-certain and the other follows by elimination.
- **`via` node:** the deepest direct ancestor shared DNA must have passed
  through. For a couple MRCA (2k, 2k+1), it is k.
- **Shared copies:** a label from one sibling's match applies to every
  sibling carrying that copy at that position.
- **Ancestral crossover edge:** adjacent incompatible labels on one copy
  imply a crossover in their deepest common node's meiosis.
- **Residual ends:** segment ends the tester's own painting does not
  explain. Ends shared by matches from different branches suggest a
  crossover on the tester's own copy; ends unique to one match's family
  belong to that branch, and when several of its matches share them they
  pin one ancestor's meiosis.
- **Placement:** assigning a match segment to a grandparent copy (or, for
  matches descending from a grandparent couple, only to a side). The
  placement likelihood uses absence too: a real segment appears in exactly
  the siblings carrying that copy. It is combined with deep labels and a cM
  prior, and reported as nested subtree mass.
- **Support:** for a painted block, the match segments placed on it and how
  many tree-linked ones agree (✓) or disagree (✗) with its grandparent; for
  a shared-match edge, reported / observable runs.
- **Confirmed identity:** a match joined to a tree person by hand
  (`[[identity]]` in `family.toml`), as opposed to a join by name, which is
  weak because names repeat.
- **Match identity:** MyHeritage IDs (`D-<donor kit>-D-<match kit>`) are a
  strong cross-donor key; FTDNA gives names only.
- **Identical twins:** one genome, two persons. A twin's child is
  genetically a half-sibling of the co-twin's children.
- **Groups = anonymous couples:** "siblings of X" links to one, possibly
  unnamed, couple, which pools its members' evidence.
- **Pile-up flag:** the top 5% of 1 Mb bins by match coverage per donor. A
  cM/Mb below about 0.35 flags segments spanning a centromere.
- **Triage by information value:** ask about the matches whose answer most
  changes the model.
- **Stay:** one person at one place for a period, aggregated from repeated
  residence entries and household-examination citations.
- **Volume and reference code:** an archive volume as Riksarkivet writes it
  (series/volume, `A II a/3`) within an archive identified by its reference
  code (`SE/VALA/00204`).
- **Congregation (församling):** the unit the church books were kept by,
  dated; distinct from the socken (territory), the archive (kyrkoarkiv) and
  the town (stad).
- **Jordnatur:** a farm's tenure (krono, skatte, frälse): a dated attribute
  of the farm, not part of its name.
- **Erratum:** a correction kept beside the master data, with was/now, a
  source and a key that survives re-exports.
- **Footprint (of a lineage path):** the dated places of the ancestors on
  and above that path, with precision and source. Proposed, not code yet
  (roadmap: geography of matches).

## Decisions

- A probabilistic HMM rather than rule-based visual phasing: it weighs
  near-coincident crossovers instead of failing on them.
- Sides stay A/B until anchored.
- Grandparent labels are anchored by documented relatives and tree links
  (weighted votes, judged leave-one-out); DNA Painter paintings are a
  held-out check unless `[phasing] anchors` lists them. Conflicting tree
  links are listed for review.
- Store assertions with provenance, never edits to the master data.
- Personal research stays private and is backed up outside git: the
  private line of history never leaves the computer, and hand-kept files
  go to a private cloud folder.
- The project works with autosomal DNA. X is a later, separate model; Y and
  mtDNA (haplogroups, mutation rates) are out of scope.
- Inference uses autosomal segments of at least 7 cM. The loader keeps
  everything, with flags. X needs its own sex-aware model.
- GRCh37 coordinates throughout. Analysis converts to cM through a real
  genetic map, which equalises recombination across chromosomes. No extra
  per-chromosome standardisation.
- Family-specific settings (people, kits, exports, anchors) come from
  `family.toml`, which stays private; `examples/family.example.toml` shows
  the format. Code holds no names.
- Data sources: GEDmatch, FTDNA and MyHeritage exports, plus raw data
  borrowed with recorded consent. MyHeritage has crippled its bulk segment
  export, so new MyHeritage data arrives as selective chromosome-browser
  captures of chosen matches; `myheritage_io` reads that format and `kits`
  marks such exports partial.
- Public documents use generic examples only.
- Positioning: the integrating layer. Phase-aware, copy-specific inference
  is the gap no current tool fills.
- Match-space clustering (Jaccard on intervals, binned occupancy, UMAP or
  MDS, Leiden or spectral clustering on overlap graphs) is an exploratory
  view, not the primary method. It runs only after side or copy assignment
  and pile-up masking, because unphased overlap mixes both parents at every
  locus and pile-ups dominate it. Gaussian smoothing over bins is for
  display only, since segment ends carry the inferential signal.
- Jordnatur is a dated attribute of a farm, not part of its name. Written
  beside a name ("Possarp Skatte") it goes into the place's `jordnatur`
  list, since it can change. As a compound ("Ödeshögs Skattegård") it names
  a farm of its own; one farm under different compounds in different years
  is joined by hand with a note.
- The gazetteer's parish is the congregation, identified by its Wikidata
  item for that era. Archive, socken and town are separate entities; when
  the evidence doesn't pick a congregation, a record stays at its archive.
  Dated names and mergers are attributes of one entity, never part of a
  key; old keys become aliases. *Adopted 2026-11-10, not implemented yet:*
  it reverses the earlier folding of Gränna's lands- and stadsförsamling
  into one parish, which the gazetteer still does (roadmap: places).

## Related tools

This project reads several of these tools' outputs and leans on public
archives; it does not replace them.

| Tool | What it does | Here |
| --- | --- | --- |
| [Genetic Affairs](https://dna-explained.com/2022/02/21/autokinship-at-gedmatch-by-genetic-affairs) | AutoCluster, AutoSegment, AutoTree, AutoKinship | AutoCluster runs are read |
| [DNA Painter](https://dnapainter.com) | Manual chromosome mapping, WATO | backups are read, and the painting is written back |
| [GEDmatch](https://www.gedmatch.com) | One-to-one and one-to-many comparisons | one-to-one pages validate the phasing |
| [Borland Genetics](https://borlandgenetics.blogspot.com/2024/09/explore-advanced-chromosome-mapping.html) | Ancestor DNA reconstruction from relatives' raw data | a different route to grandparent copies |
| [BanyanDNA](https://www.yourdnaguide.com/ydgblog/wato-plus-vs-banyandna) / WATO | Ranks pedigree hypotheses from shared cM | relationship hypotheses without segment positions |
| [Gramps](https://gramps-project.org) | Open-source genealogy program | opens the store's GEDCOM export |
| [Underlay](https://underlay.mit.edu) | A distributed graph of assertions with provenance | the model for how claims are stored |

Archives and open data: [Riksarkivet](https://riksarkivet.se), [Wikidata](https://www.wikidata.org), [OpenStreetMap](https://www.openstreetmap.org).
