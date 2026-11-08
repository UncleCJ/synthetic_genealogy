# Synthetic Genealogy — 2026 revision

Carl-Johan Sveningsson · revised November 2026 · current state, decisions and next steps: [CHECKPOINT.md](CHECKPOINT.md)

Most of the genetic half of the 2020 enumeration has since become designable, and a few parts now exist as tools; the integrating layer still does not. This revision keeps the original facets from [Synthetic Genealogy.md](https://gist.github.com/UncleCJ/6f9b36f55214e1d9ca5d128a9854e9f3) (October 2020) and marks each item by where it stands in 2026.

Status words used throughout:

- **Matured** — available in tools people use today.
- **Designed** — a concrete method exists (sketched or published), not yet a usable tool.
- **Open** — still an idea or an unsolved problem.

Two facets are new: evidence and hypotheses, and consent and privacy. Both cut across every other facet, so they sit in the foundations section rather than in the list.

## Foundations across all facets

Every facet produces claims that can conflict, so the store of record should hold assertions with provenance, never a single "true" tree. Four foundations follow from that.

### Assertions with provenance

Each statement records what was claimed, by whom, from which source, with what confidence and when. The tree, chromosome paintings and placements are views derived from the log and recomputed when it changes.

This is the core idea of the [Underlay](https://underlay.mit.edu) from MIT's Knowledge Futures Group (Danny Hillis, SJ Klein, Travis Rich, Joel Gustafson). It stores contested or contradictory statements together with their context and chains of provenance, leaving evaluation to separate layers. Their own illustration is genealogical: a [short intro](https://notes.knowledgefutures.org/pub/underlay-short-intro) cites Gracie Allen's claimed birth year against the census, both kept with sources.

Wikibase offers the same shape in practice: statements with qualifiers, references and ranks, plus SPARQL. A self-hosted Wikibase keeps private families private while linking public anchors (parishes, farms, events) to Wikidata.

### Evidence and hypotheses (new facet)

Competing claims, confidence and conflict detection apply to documents and DNA alike. A hypothesis is an explicit object ("the man named in the records was her biological father") that evidence supports or contradicts, with the reasoning kept.

### Consent and privacy (new facet)

Borrowed raw data, matches' segment lists and living relatives in a shared graph all need recorded consent that can be withdrawn. Under GDPR, genetic data is a special category. Consent is itself stored as an assertion.

### One interval engine

Allen's interval algebra appears twice in the 2020 list, under phasing and under chronology. Chromosome segments and life events are both intervals on a line, so one engine with fuzzy endpoints could reason about both: "this segment lies within a great-grandmother's paternal copy" and "the adoption falls between her birth and the next household examination" are the same kind of constraint.

## Family trees

The "unified mesh out of the mother-father-child motif" is now a concrete data model: a pedigree graph where unknown people are anonymous nodes, and groups are simply shared parents.

| 2020 item | Status | Where it stands |
| --- | --- | --- |
| Unified mesh from the mother-father-child motif | Designed | Pedigree graph (not a tree) allowing collapse; anonymous persons stand in for unknowns; "these are siblings of my uncle" = linked to one, possibly unnamed, couple |
| Hard, factual relationship structure | Designed | Every link is an assertion with source and confidence, never a bare edge |
| Higher-order methods (ARGs, tree sequences) | Designed | Inferred transmissions (parent, child, chromosome, left, right) map onto tskit's edge table; msprime's fixed-pedigree mode and Ped-sim simulate a known tree for calibration |
| GEDCOM, new formats, proprietary trees | Matured, with friction | GEDCOM still the exchange format; moving trees between services (for example MyHeritage to Gramps) often needs cleanup scripts to avoid losing data |
| Other genealogists' trees | Matured | Genetic Affairs AutoTree and AutoKinship reconstruct trees from matches' shared trees |
| More or less reliable public collections | Matured | Wikidata for notable people; WikiTree links to it; private families need their own Wikibase or Gramps |

**Coordinates.** Ahnentafel numbers address our direct line (father 2n, mother 2n+1). They index paths, not people: under pedigree collapse one person holds several numbers, which is genetically correct because DNA travels along paths. Collateral relatives get the ancestral couple plus a downward path ("9 ↓ 2nd child ↓ 1st child"). With several donors, each has an own Ahnentafel view of one shared graph.

**Store of record (open question).** Gramps is a common working home for serious hobbyists; Wikibase fits the assertion model and Wikidata links better. One may be the store and the other a view.

## Genetics

The 2020 list anticipated the whole method: fuzzy sibling phasing, crossovers from segment edges, grandparent mosaics and recursive ancestor deduction. What changed is that each now has a concrete design, while data access at the vendors has narrowed.

| 2020 item | Status | Where it stands |
| --- | --- | --- |
| Phasing, "fuzzy" for three full siblings | Designed | An inheritance-vector HMM (Lander-Green) decodes grandparent painting and attributes each crossover; near-coincident crossovers that break manual visual phasing are weighed, not decided. No open-source automated visual phasing found |
| Learn crossover loci from segment edges | Designed | Segment ends not explained by our own painting are residuals on the match's branch; shared residuals across matches of one branch pin a specific ancestor's meiosis |
| Learn grandparent mosaic, reconcile with matches | Designed | Known relatives anchor each chromosome's side and copy labels; labels propagate to every sibling carrying that copy |
| Deduce ancestor contributions recursively | Designed | Visual phasing one generation up: a grandparent's many children, represented by their tested descendants, separate that grandparent's own two copies |
| Sex chromosomes, mitochondria, X-match constraints | Matured (Y, mt) / Open (X in models) | Mitotree and haplotypes released 2025; X needs its own sex-aware model in the phasing design |
| Crossover probability, sperm vs egg | Designed | Sex-specific maps (female meioses about 1.6x more crossovers, placed differently) weakly reveal which parent transmitted |
| Estimated relationship ("what are the odds") | Matured | WATO plus, BanyanDNA (2024): pedigree hypotheses ranked from shared cM, including half and double relationships |
| Clustering of common matches | Matured | Genetic Affairs AutoCluster, AutoSegment (triangulated, segment-based), AutoSegment Split (2026: opposite sides) |
| Triangulation | Matured, data-limited | Needs "matches match each other on the same segment"; GEDmatch is now the main place showing that |
| DNA painting / chromosome browser | Matured | DNA Painter; Borland HIR Mapper and Segment Lab |
| Actual SNP sequences, deduce ancestor segments | Matured | Borland Genetics reconstructs ancestor kits from descendants' raw data |
| Pitfall: population segments | Partly matured | Pile-up region masking (Li et al. 2014) is an option in AutoSegment |
| Clustering within one phased copy | Open | Overlap similarity (Jaccard, interval graphs, UMAP/Leiden) becomes meaningful only after segments carry a side or copy label and pile-ups are masked; unphased, it mixes both parents at every locus |

**Data access is the main constraint.** Ancestry shows no segments and blocks third-party tools; 23andMe no longer shows matching segments; MyHeritage stopped accepting uploads in 2025. A system now rests on GEDmatch, FamilyTreeDNA and MyHeritage segment exports, plus raw data borrowed with consent.

**The integrating gap.** No tool combines grandparent-level phasing, labels that propagate across siblings, and placement that predicts which relatives should and should not match. A full- versus half-sibling test on one specific ancestral copy cannot be expressed in any current tool.

## Records, history and populations

The documentary facets have moved mostly through AI reading and transcription; structuring them into linked, sourced assertions is still largely manual. Status here is from general knowledge rather than a fresh survey.

| 2020 item | Status | Where it stands |
| --- | --- | --- |
| Accessibility: proprietary, subscription, compilations | Matured | Swedish church records largely digitised (Riksarkivet, ArkivDigital); Stockholm's Rotemansarkivet covers about 1878 to 1926 |
| Digitise: scan, OCR, index | Matured | Handwritten-text recognition now reads older scripts usefully; indexing still uneven |
| Structure archives and contents | Open | Turning transcriptions into sourced assertions about people, places and events is the bottleneck |
| Graves: catalogues, inventory | Matured | Grave inventories and photo catalogues are widely available |
| Legal records, libraries, news, portraits | Partly matured | Digitised newspapers searchable; legal and police records mostly by archive visit or request |
| Referencing, quoting, authorities | Designed | Every assertion carries its source; authority records via Wikidata identifiers |
| Private knowledge, photos, anecdotes | Open | Same assertion model, with the teller and date as provenance |
| Locations, proximity, migration | Partly matured | Wikidata covers parishes and many farms; historical boundaries change over time |
| Events, chronology, causality, duration | Designed | The shared interval engine from Foundations |
| Entities and borders: countries to farms | Partly matured | Parish and county changes are documented but rarely machine-readable as time-bounded intervals |
| Populations: location-centric genealogy, statistics, coverage | Open | Coverage of knowledge (which parishes and decades are well researched) is an unexplored, measurable layer |

**Documents and DNA on one graph.** A police report, letters and parish records become dated, sourced assertions beside the DNA evidence, so both weigh in on the same hypothesis.

## Health and forensics

Both facets are technically mature elsewhere and ethically the most sensitive, so they belong outside the core system unless consent is explicit.

| 2020 item | Status | Where it stands |
| --- | --- | --- |
| Heritable disease, susceptibilities | Matured, outside genealogy | Vendor health reports and open-source raw-data analysers exist; clinical interpretation needs professionals |
| Other phenotypes, appearance | Open | Prediction from genotype remains weak beyond a few traits |
| Forensic: pinpoint ancestors of perpetrators | Matured, contested | Investigative genetic genealogy is routine in some countries, governed by database opt-in rules |

**Boundary for this project.** Health findings about relatives, and any forensic use, require each person's explicit consent. Neither should flow from borrowed data by default.

## Landscape 2026

Each piece of the vision exists somewhere, but in separate tools that reason from different evidence; none reasons from phased grandparental copies.

| Tool | What it does | Evidence it reasons from | Missing for this vision |
| --- | --- | --- | --- |
| [Genetic Affairs](https://dna-explained.com/2022/02/21/autokinship-at-gedmatch-by-genetic-affairs) (Evert-Jan Blom) | AutoCluster, AutoSegment, AutoTree, AutoKinship, AutoPedigree, AutoSegment Split | Shared matches, triangulated segments, matches' trees | Phase-aware, copy-specific inference |
| [Borland Genetics](https://borlandgenetics.blogspot.com/2024/09/explore-advanced-chromosome-mapping.html) (Kevin Borland) | Ancestor DNA reconstruction, sibling phasing, phase maps | Raw data of many relatives | Placement of new matches; hypothesis testing |
| [AncestryDNA SideView](https://www.ancestry.com/lp/telling-parents-matches-apart) | Parental-side phasing from the match network | Ancestry's own matches | Grandparent level; no segments; no third-party access |
| [BanyanDNA](https://www.yourdnaguide.com/ydgblog/wato-plus-vs-banyandna) / WATO plus | Ranks pedigree hypotheses, incl. half and double relationships | Shared cM between tree members | Segment positions |
| DNA Painter | Manual chromosome mapping, WATO | Segments the user paints | Automation |
| [apriha/lineage](https://github.com/apriha/lineage) | Open-source IBD1/IBD2 detection between raw files | Raw data | Phasing and inference on top |
| [Gramps MCP](https://pypi.org/project/gramps-mcp-full/) | Exposes a Gramps tree to AI agents, incl. DNA segment parsing | Tree and segment data | Genetic inference |
| [autoresearch-genealogy](https://github.com/mattprusak/autoresearch-genealogy), [Kinprove recipes](https://github.com/Kinprove/genealogy-research-recipes) | AI research workflows and guardrails for Claude | Records, match lists | Computation |
| [Underlay](https://underlay.mit.edu) (KFG) | Distributed graph of assertions with provenance | Any structured claims | Genealogy-specific model |

As of 2022, Louis Kessler [doubted visual phasing could be fully programmed](https://beholdgenealogy.com/blog/?p=3878); a probabilistic decoder answers his main objection.

## A first use case: contested paternity

A contested paternity a few generations back exercises every part of the design at once. Take a typical case: a great-grandmother's father denied paternity, while acknowledging her older sisters; records survive, descendants of all the sisters can test, and one DNA match descends from the named man's family. The question is two-way: was he her father, or a stranger?

1. Phase a sibling set of her descendants to grandparent level. Extra testers sharpen it; a cousin whose parent is an identical twin of the siblings' parent counts genetically as a half-sibling.
2. Anchor each chromosome's side and copy labels with known cousins.
3. Phase one generation up: her children, represented by their tested descendants, separate her two original copies, one from each of her parents.
4. Run the sister test. Acknowledged sisters' descendants matching on both of her copies means full sisters, so the same father; matching on one copy only means maternal half-sisters.
5. Check the match from the named man's family against a prediction: its segments must fall on her paternal copy, and appear in exactly the cousins who carry that copy there.
6. Record documents and DNA as assertions on one hypothesis object, and calibrate the expected signal by simulating the actual pedigree (Ped-sim or msprime).

Open questions:

- How many tested descendants per sister make the sister test decisive? Simulation can answer this before anyone tests.
- Gramps or Wikibase as store of record?
- Which existing tool could host the inference engine as a module rather than starting a new application?
