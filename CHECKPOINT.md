# Checkpoint — November 2026

Read this after [README.md](README.md), which holds the concepts and the landscape. This file holds the working state: terms, decisions, code and next steps. It merges three sessions: two with Claude (sibling phasing and placement, and housekeeping) and one with Gemini (match-space representation). Personal data never reaches the public line: it lives in `data/` and in one private commit (see [WORKFLOW.md](WORKFLOW.md)).

## Working vocabulary

These terms are used in code and discussion. They are not all spelled out in the README.

- **Inheritance vector:** for n siblings, which grandparental copy each carries relative to sibling 1, giving 4^(n−1) states (16 for three). A Lander–Green HMM decodes it along each chromosome with Viterbi.
- **Crossover attribution:** if both relative bits on one side flip, sibling 1 recombined. If one bit flips, sibling 2 or 3 did.
- **Side A/B, copy 0/1:** unanchored labels. Siblings alone cannot tell paternal from maternal, or grandfather from grandmother, which leaves 8 labellings per chromosome. Known relatives resolve them ("anchoring").
- **`via` node:** the deepest direct ancestor shared DNA must have passed through. For a couple MRCA (2k, 2k+1), it is k.
- **Shared copies:** a label from one sibling's match applies to every sibling carrying that copy at that position.
- **Ancestral crossover edge:** adjacent incompatible labels on one copy imply a crossover in their deepest common node's meiosis.
- **Residual ends:** segment ends our own painting does not explain. They belong to the match's branch, and when several matches share them, they pin one ancestor's meiosis.
- **Placement likelihood:** a real segment appears in exactly the siblings carrying that copy, so absence is evidence too. It is combined with deep labels and a cM prior, and reported as nested subtree mass.
- **Tested parent:** sorts matches by side directly. In raw-data phasing it makes that side near-certain and the other follows by elimination.
- **Identical twins:** one genome, two persons. A twin's child is genetically a half-sibling of the co-twin's children.
- **Groups = anonymous couples:** "siblings of X" links to one, possibly unnamed, couple. That couple pools its members' evidence.
- **Snapshots:** one per export, donor and vendor, dated. Re-imports are diffed.
- **Match identity:** MyHeritage IDs are `D-<donor kit>-D-<match kit>`, a strong cross-donor key. FTDNA gives names only, which is weak (names repeat).
- **Pile-up flag:** the top 5% of 1 Mb bins by match coverage per donor. A cM/Mb below about 0.35 flags segments spanning a centromere.
- **Triage by information value:** ask the user about the matches whose answer most changes the model.

## Decisions

- A probabilistic HMM rather than rule-based visual phasing: it weighs near-coincident crossovers instead of failing on them.
- Sides stay A/B until anchored.
- Store assertions with provenance, never edits. Consent is an assertion too, so withdrawal is clean.
- Inference uses autosomal segments of at least 7 cM. The loader keeps everything, with flags. X needs its own sex-aware model.
- GRCh37 coordinates throughout. Analysis converts to cM through a real genetic map, which equalises recombination across chromosomes. No extra per-chromosome standardisation.
- Family-specific settings (people, kits, exports, anchors) come from `family.toml`, which stays private; `family.example.toml` shows the format. Code holds no names.
- Data sources: GEDmatch, FTDNA and MyHeritage exports, plus raw data borrowed with recorded consent. MyHeritage has crippled its bulk segment export, so new MyHeritage data arrives as selective chromosome-browser captures of chosen matches. `myheritage_io` reads that format (one-to-many "Download shared DNA info"), and `kits` marks such exports partial.
- Public documents use generic examples only. The contested-paternity use case is cleared for publication.
- Positioning: the integrating layer. Phase-aware, copy-specific inference is the gap.
- **Match-space clustering is an exploratory view, not the primary method.** It covers Jaccard distance on intervals, binned occupancy, UMAP or MDS, and Leiden or spectral clustering on overlap graphs. It runs only after side or copy assignment and pile-up masking, because unphased overlap mixes both parents at every locus and pile-ups dominate it. Gaussian smoothing over bins is for display only, since segment ends carry the inferential signal.

## Code state

| File | State |
|---|---|
| `segments.ipynb` | In git (2021). `chr_bplen` is too short (chr1 about 214 Mb vs 249.25 Mb), so the heatmap drops distal segments. Its rename map predates current export headers. Names and match IDs are pseudonymised in its current state; history is kept as is. Sketch-era work, to be retired. |
| `ftdna_io.py`, `myheritage_io.py` | In git. Vendor readers (replace the planned `segments_io.py`). FTDNA: Family Finder match list and chromosome-browser export, joined on a whitespace- and case-normalised `match_key`; duplicate names flagged `ambiguous`. MyHeritage: Swedish 2020 and 2021 bulk headers, English headers and the 2026 one-to-many selection export (with its triangulated rows read separately); `match_key` is the match half of `D-…-D-…`, or `name:<name>` without an ID. Columns: `subject, match, match_key, chrom, start, end, cM, snps, source` (+ `tester_kit`, RSIDs for MyHeritage). Not yet: `DonorRegistry`, `snapshot_diff`, `add_quality_flags`, `GRCH37_LEN`. |
| `config.py`, `kits.py` | In git. `config` loads `family.toml`; `kits.load` builds one kit per `[[segment_exports]]`, drops the family's own kits by whole name or MyHeritage kit (`family_filter`: `family_names`, `family_kits`), groups by platform, and keeps partial (selection) exports in their own group. |
| `visual_phasing.py` | In git (was `visual_phasing_sketch.py`). Inheritance-vector HMM, FIR/HIR/NIR view, grandparent painting, raw-file loader, `merge_sibs`, `run(donor_files)`. |
| `phasing_labels.py`, `documented_anchors.py`, `dnapainter_io.py` | In git. Anchor sides A/B and copies 0/1 with the tested mother's kit, documented relatives (`[[anchors]]`) and DNA Painter cluster paintings read as assertions; per-assertion verdicts and a grandparent painting. |
| `match_placement.py`, `revelations.py` | In git (cover the planned `segment_placement_sketch.py`). Place children's and the mother's matches on grandparents, 2 Mb pile-up bins, cross-checks, report. `segment_placement.py` is an empty, git-ignored placeholder. Nested-posterior placement and deep labels beyond grandparents are not built yet. |
| `research_log.py`, `research/` | In git (schema and tool; entries are private). Questions, hypotheses, segments, findings and notes with lineage codes; `research/INDEX.md` is generated. |
| `README.md` | Replaced by the 2026 revision. The 2020 outline remains in git history. |

Loader check (2026-11-08), on a sibling's 2023 FTDNA export: the raw file has 7,216 rows, one an exact duplicate. The readers now drop exact duplicates with a counted message (7,215 rows). `match_key` merges two case-only name variants. The old `family_regex` held a bare first name and also dropped 26 rows of unrelated matches; the whole-name and kit filter that replaced it drops only the family's own kits (102 rows). The earlier figure of 7,202 can't be reproduced with the code in this repo.

## Next steps

1. Commit this checkpoint and the pseudonymised notebook (the Python modules are already in git). Retire the sketch-era notebook once the vendor readers and a `GRCH37_LEN` table replace it.
2. Raw data: three kits have 2021 FTDNA build-37 downloads and one has a 2023 o37 file; download the fourth kit afresh if its chip differs. Check chip overlap. Extend the HMM with the tested parent (trio plus siblings).
3. Run the readers on the full archived exports. MyHeritage covers all three siblings and the tested parent, so trio-plus-siblings analysis can start at segment level before any raw data arrives. Compare pile-up bins with published pile-up regions.
4. Calibrate on simulated pedigrees (Ped-sim, msprime fixed pedigree): how reliable residual ends are, and how many testers per branch make the full/half-sibling test decisive.
5. Recruit testers for the use case: descendants of each sister line, plus paternal cousins.
6. Add the genetic-map interpolation (bp to cM) and an interval tree as the shared interval engine.
7. After step 2: build the exploratory per-copy match-space view (Jaccard on cM intervals, pile-ups masked).
8. Choose the store of record: Gramps or self-hosted Wikibase, with the other as a view.
9. Close the model gaps: X chromosome, sex-specific maps, an HMM within segments instead of bins, half relationships, endogamy.
10. Done: reader for selective MyHeritage chromosome-browser captures (`myheritage_io`). Still to do: verify the unverified formats with real samples. Design the triage and group UI. Evaluate a friend's tool as a host for the engine.
