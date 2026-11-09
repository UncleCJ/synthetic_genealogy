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
| `config.py`, `kits.py` | In git. `config` loads `family.toml`; `kits.load` builds one kit per `[[segment_exports]]`, drops the family's own kits by whole name or MyHeritage kit (`family_filter`: `family_names`, `family_kits`), groups by platform, and keeps partial (selection) exports in their own group. An export newer than the mother's can name an `earlier` export of the same kit: matches already in it may still be called paternal by absence from the mother's list. |
| `visual_phasing.py` | In git (was `visual_phasing_sketch.py`). Inheritance-vector HMM, FIR/HIR/NIR view, grandparent painting, raw-file loader, `merge_sibs`, `run(donor_files, parent=, ibd=)`. A tested parent's genotypes enter the emissions (as side B), and `ibd` intervals (two siblings share a segment end to end with a match) add soft same-copy evidence (`IBD_LAMBDA` per merged interval). On the family data: parent agreement ≥ 99.8% on every chromosome, sibling consistency on held-out shared segments 93.8% → 97.1%, crossovers 183 → 190. |
| `phasing_labels.py`, `documented_anchors.py`, `dnapainter_io.py` | In git. Anchor sides A/B and copies 0/1 with the tested mother's kit, documented relatives (`[[anchors]]`) and DNA Painter cluster paintings read as assertions; per-assertion verdicts and a grandparent painting. |
| `match_placement.py`, `revelations.py` | In git (cover the planned `segment_placement_sketch.py`). Place children's and the mother's matches on grandparents, 2 Mb pile-up bins, cross-checks, report. `segment_placement.py` is an empty, git-ignored placeholder. Nested-posterior placement and deep labels beyond grandparents are not built yet. |
| `research_log.py`, `research/` | In git (schema and tool; entries are private). Questions, hypotheses, segments, findings and notes with lineage codes; `research/INDEX.md` is generated. |
| `gedcom_io.py` | In git (sketch). GEDCOM 5.5.1 reader (tested on one Gramps 5.1 export): people, families, PEDI (adopted/foster links kept but left out of genetic paths), MyHeritage `FACT MH:I<n>` aliases. Lineage codes and Ahnentafel numbers from a proband (`[gedcom]` in `family.toml`), descendants, closest shared ancestors, and `matches`: tree people joined to placed matches by full name, with tree side vs DNA placement. Name joins are weak; a hit is a candidate. |
| `dnapainter_export.py` | In git (sketch). Writes the computed painting back as DNA Painter backups, one profile per tester: phased grandparent blocks (pale) and placed match segments (≥ 12 cM; tree-linked matches ≥ 7 cM, in the group of the deepest ancestor the tree gives, if it agrees with the placement). Groups use the lineage-code naming `dnapainter_io` reads, so an edited backup can come back in as assertions. Also one PNG per tester. For looking, not evidence: pile-ups are not masked. |
| `icw_io.py`, `icw_phasing.py` | In git (sketch). Shared-match (ICW) edges from Genetic Affairs AutoCluster CSVs, its node/edge CSVs and FTDNA in-common-with lists (`[[icw]]` in `family.toml`). `icw_phasing` checks them against the segment placement: how often shared matches vote the same grandparent (validation), candidate placements for unplaced matches, pairs placed on different parents' sides, cluster composition, and deeper-lineage hints from tree-linked shared matches. Output `icw_report.md` and low-weight `assertions_icw.csv`. Couple-level matches (split placement, or a tree MRCA couple at grandparent level) are labelled by side and vote by side; for an unplaced match the ICW vote settles the side and its own unresolved segments, read on that side, pick the grandparent or the couple. The couple test pools the siblings' placed DNA per match (`pooled_couples`). |
| `sibling_consistency.py` | In git (sketch). Segments two siblings share end to end with a match (same parent's side, Jaccard ≥ 0.9, ≥ 10 cM) must lie on the same grandparent copy; lists where the painting disagrees, and relabels short blocks (< 1,500 SNPs) that ≥ 2 pairs outvote and none support. Writes `phasing_grandparent_segments_corrected.csv`, which `match_placement.load_painting` prefers while it is newer than `phasing_labels.py`'s output. Large conflicts point to misplaced crossovers and need the HMM, not relabelling. |
| `pipeline.py`, `PIPELINE.md` | In git. `pipeline.py` runs the chain in order (DNA Painter → anchors → phasing → placement → consistency → placement → ICW → export → GEDmatch validation → research index) and appends each step's summary to `data/pipeline_log.md`. `PIPELINE.md` walks through every tool with an anonymised run. |
| `gedmatch_io.py` | In git. Reads saved GEDmatch one-to-one pages; compares the model's sibling-pair state (NIR/HIR/FIR) with GEDmatch's, by base pairs. On the family's 2020 comparisons: 93.2% (91.6% before the mother entered the model); fully identical regions agree almost entirely. |
| `match_graph.py` | In git (sketch). Merges all MyHeritage AutoCluster runs into one graph keyed by match ID; each pair carries `observable` (runs where both were in the window) and `reported`, so support = reported / observable and runs with different thresholds don't distort it. Bipartite tester → match layer; placement pooled over siblings as node colour. GEXF for Gephi plus PNGs. On the family's runs: 198 of 268 edges between placed matches join the same grandparent (71 expected by chance), assortativity 0.59. |
| `prospects.py` | In git (sketch). Research shortlist: matches ≥ 60 cM with a sibling (≥ 90 with the mother) not in the GEDCOM (strict name join, plus a looser given-name-and-surname check), with side, placed and tree-linked shared matches as branch hints, rough relationship and the match's own tree link. |
| `places.py` | In git (sketch). Reads Riksarkivet citations (`SE/VALA/00472/A I/11 (years), bildid, sida`) and MyHeritage volume labels (`Bok: <parish> AI7`) from the GEDCOM, resolves archive codes to Wikidata parish items, walks a parish's history and lists candidate parishes for a name. Wikidata answers are cached in `gazetteer/cache/` (not committed: large). On one tree, all 34 parish archive codes resolve; one police archive has no item. Not yet: county, härad and diocese at an event's date; farm-level places (TORA). |
| `textfix.py` | In git. Repairs å/ä/ö damaged in vendor exports, used by the GEDCOM, FTDNA and MyHeritage readers: decomposed letters (NFC), spacing marks ("Ka¨lleryd", "Stora A°by"), mojibake read as Windows-1252 or Latin-1 ("SkÃ¶vde", "Ã\x85kesson", and Å whose second byte became a newline or `<br/>`). |
| `volumes.py`, `riksarkivet.py` | In git (sketch). The research as it sits in the record volumes: every citation reduced to parish, series/volume (written `A II a/3`, as Riksarkivet does), page, farm and a tidiness tier (Riksarkivet citation, image link, MyHeritage record, index, tree, place only). Each volume gets its reference code (parish archive from the tree's tidied citations, else Riksarkivet's search by archive name) and, through Riksarkivet's open OAI service, its years, content note ("I. 1 - 250. Södra delen") and viewer link. Flags a MyHeritage label that disagrees with a pasted citation, and image ids from another image series. Output: `data/volumes.html` (volumes as page strips; People tab), `data/volume_refs.csv`. |
| `gazetteer.py`, `gazetteer/` | In git (sketch); the gazetteer itself is public. Parishes (archive code, Wikidata item, coordinates, aliases) and villages, farms, rotar and torp keyed `Parish/Name`, with `within`, `kind` and every written form as a variant. Built from record citations and pre-1950 place strings (no digits or streets); a rebuild only adds and fills, until stable. Written names are split into rote/farm/torp ("Roten Ingarp Rote Swenshult" → Svenshult within Ingarps rote). Clear spelling variants merge automatically within a parish (e/ä, o/å/ö, kj/k, -gården/-gård, cut-short gård, genitive s, joint s/d), named in the least redundant modern form; neighbour farms (Väster/Öster, Stora/Lilla) never merge. The rest are proposals in `data/gazetteer_todo.md`. Raw place strings map through a private `data/plac_map.toml`. |
| `errata.py` | In git. Corrections and notes beside the MyHeritage master, never in it, keyed by ids that survive re-exports (MyHeritage record, Riksarkivet image, volume, person, place). Each run reports a fix as applied, retired (fixed upstream), conflict or orphan. The file is private (`data/errata.toml`); `errata.example.toml` shows the format. Person facts are keyed but not yet applied. |
| `residences.py` | In git (sketch). Residence histories from household-examination citations (A I, A II a): stays merged across volumes, gaps with the next volume to open, moves between parishes bracketed by overlapping volume years, and stays not yet collated as residence events in the tree. On one tree: 791 people, 273 moves, 376 gaps, 59 uncollated stays. |
| `README.md` | Replaced by the 2026 revision. The 2020 outline remains in git history. |

Loader check (2026-11-08), on a sibling's 2023 FTDNA export: the raw file has 7,216 rows, one an exact duplicate. The readers now drop exact duplicates with a counted message (7,215 rows). `match_key` merges two case-only name variants. The old `family_regex` held a bare first name and also dropped 26 rows of unrelated matches; the whole-name and kit filter that replaced it drops only the family's own kits (102 rows). The earlier figure of 7,202 can't be reproduced with the code in this repo.

## Side project: face avatars (not yet in the repo)

A pure-Python module, `genealogy_avatars/`, was built in a claude.ai chat. It hasn't been reviewed or added here yet. It has:

- an offline SVG cartoon renderer, styled by the photo's era;
- a GEDCOM 5.5.1 loader (Swedish call names marked `*`, MyHeritage RIN facts, citation texts and links);
- a pedigree relationship matrix (Henderson's tabular method) with **identical-twin support**: the second twin copies the first's row, and descendants follow;
- an optional shared-cM override (cM/6800, nearest positive-definite repair);
- BLUP / Gaussian-process spreading of photo-derived face vectors over the kinship matrix, so unphotographed relatives get shrunken estimates with uncertainty. Validated only on simulated pedigrees: r ≈ 0.4 for a parent, about 0.15 for a cousin.

**Decision:** each photo record carries side data, and a `trusted()` rule set decides which measurements survive:

- faces under about 100 px tall: no geometry;
- head turned more than about 15°: vertical ratios only;
- open mouth: no mouth width;
- full beard: no face width, face length or mouth width;
- dim light, greyscale or sepia, or AI-colourised photos: no colours;
- transient appearance (glasses, beard, clothes) is drawn but never inherited.

**Finding:** in one person's two frontal photos 14 years apart, only nose length clearly exceeds photo-to-photo noise (reliability about 0.9). Face ratio, eye spacing and brow height are near noise, so inference should weight nose length and reliable colours most.

**Privacy:** per-person face records are biometric data. They stay private like segment data; only generic code can go public.

## Next steps

1. Commit this checkpoint and the pseudonymised notebook (the Python modules are already in git). Retire the sketch-era notebook once the vendor readers and a `GRCH37_LEN` table replace it.
2. Raw data: three kits have 2021 FTDNA build-37 downloads and one has a 2023 o37 file; download the fourth kit afresh if its chip differs. Check chip overlap. Done (2026-11-09): the HMM takes the tested parent (trio plus siblings).
3. Partly done (2026-11-09): the 2023 MyHeritage bulk exports for three siblings and one sibling's 2023 FTDNA export are loaded; the parent's newest MyHeritage export is 2021. Run the readers on the remaining archived exports. MyHeritage covers all three siblings and the tested parent, so trio-plus-siblings analysis can start at segment level before any raw data arrives. Compare pile-up bins with published pile-up regions.
4. Calibrate on simulated pedigrees (Ped-sim, msprime fixed pedigree): how reliable residual ends are, and how many testers per branch make the full/half-sibling test decisive.
5. Recruit testers for the use case: descendants of each sister line, plus paternal cousins.
6. Add the genetic-map interpolation (bp to cM) and an interval tree as the shared interval engine.
7. After step 2: build the exploratory per-copy match-space view (Jaccard on cM intervals, pile-ups masked).
8. Choose the store of record: Gramps or self-hosted Wikibase, with the other as a view.
9. Close the model gaps: X chromosome, sex-specific maps, an HMM within segments instead of bins, half relationships, endogamy.
10. Done: reader for selective MyHeritage chromosome-browser captures (`myheritage_io`). Still to do: verify the unverified formats with real samples. Design the triage and group UI. Evaluate a friend's tool as a host for the engine.
11. Places as dated assertions on Wikidata parish items. Wikidata's model:
    - an old parish (socken, with an ATA code) splits in 1863 into a civil municipality and a church parish (församling);
    - the församling carries the Riksarkivet archive code (P5324) and a parish code (P778) with dates of validity;
    - from 2016 a registration district (distrikt) takes over.

    Resolve places by archive code first (exact), then by volume label, then by name. Names are ambiguous ("Ryr" is four parishes) and abbreviated ("N. Ryr", "W. Ryr"), so they only give candidates. Still to do:
    - add the missing historical aliases on Wikidata (for example "Norra Ryr" for Lane-Ryr; Väne-Ryr already has "Södra Ryr");
    - get county and diocese at an event's date (socken P131 has no dates);
    - look into TORA (P14316 `tora/…`) for farms.
12. Before writing more readers:
    - a rerunnable manifest of the Drive-synced archive folder (type, date and size per file, and which reader handles it), with its summary written to the mailbox;
    - a validation set: compare the 2020 hand-phased crossovers for the sibling set with the HMM's calls. Where they disagree, either side may be wrong;
    - next readers, in rough priority: in-common-with (ICW) lists for triangulation and per-copy clustering, then Genetic Affairs AutoCluster output, to compare with the phasing. The GEDCOM reader (`gedcom_io`) exists; seeding `family.toml` anchors from it is still to do.
13. Records as master data (MyHeritage stays the master; corrections live beside it):
    - review the gazetteer proposals (`data/gazetteer_todo.md`): rote prefixes ("Eller Skog …", "Qdra. Eller Näs …") and `within` links first; mark reviewed entries `checked = true`;
    - apply `errata.py` person-level fixes (dates, names) in `gedcom_io`;
    - collate the uncollated stays and open the gap volumes `residences.py` lists;
    - add `volumes.py`, `gazetteer.py build` and `residences.py` as steps in `pipeline.py`.
