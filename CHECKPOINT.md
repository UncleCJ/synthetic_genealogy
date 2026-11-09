# Checkpoint — November 2026

Read this after [README.md](README.md), which holds the concepts and the landscape. This file holds the working state: terms, decisions, code and next steps. [PIPELINE.md](PIPELINE.md) walks through the tools in run order, with an anonymised run. It merges three sessions: two with Claude (sibling phasing and placement, and housekeeping) and one with Gemini (match-space representation). Personal data never reaches the public line: it lives in `data/` and in one private commit (see [WORKFLOW.md](WORKFLOW.md)).

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
- **Jordnatur is a dated attribute of a farm, not part of its name.** Written beside a name ("Possarp Skatte") it goes into the place's `jordnatur` list, since it can change (krono bought to skatte). As a compound ("Ödeshögs Skattegård") it names a farm of its own; one farm under different compounds in different years (Kronogård → Skattegård) is joined by hand with a note.
- A town's landsförsamling and stadsförsamling share one gazetteer parish where the records don't keep them apart (Gränna). Parishes the archive keys separately (Karlstad, Skellefteå) keep their own entries.

## Code state

What each tool does, with an anonymised example run, is in [PIPELINE.md](PIPELINE.md); module docstrings carry the details and caveats. `python3 pipeline.py` runs the chain (smoke tests first) and logs each step to `data/pipeline_log.md`. Dependencies: `requirements.txt` (core), `requirements-avatars.txt` (face package). Status words: *stable* (used on real data, checked), *sketch* (works, thresholds are judgement calls), *prototype* (shape may change). The private data folder is split into `input/`, `notes/`, `store/`, `cache/` and `output/` (what to back up, how to browse without Claude: [DATA.md](DATA.md)). Hand-kept private files are also backed up to a private Drive folder; `backup.py` lists what changed since the last backup ([WORKFLOW.md](WORKFLOW.md)). The pipeline log follows a run live, one file per run in `output/logs/`, one run at a time.

- **Readers.** `ftdna_io`, `myheritage_io` (bulk, one-to-many selections with triangulated rows apart), `family_filter`, `textfix` (å/ä/ö, mojibake, HTML entities), `config` / `kits` (exports from `family.toml`, partial selections, `earlier` exports, a mother's AutoCluster window), `dnapainter_io`, `icw_io` (AutoCluster CSVs, Gephi node/edge files, FTDNA ICW lists), `gedmatch_io` (one-to-one pages), `gedcom_io` (Gramps and raw MyHeritage exports, lineage codes, kinship over all paths with identical twins, confirmed `[[identity]]` links), `gedcom_audit` (diff two exports, redundancy audit). Stable.
- **Phasing and placement.** `visual_phasing` (inheritance-vector HMM with the tested mother in the emissions and sibling-shared segments as soft evidence; 97.1% consistent on held-out shared segments, 93.2% bp agreement with GEDmatch FIR/HIR), `phasing_labels`, `documented_anchors`, `match_placement` / `revelations` (a child's segment reaching ≥ 7 cM beyond the mother's segments with the same match is paternal, for exports of one vintage), `sibling_consistency` (short-block corrections). Stable.
- **Shared matches and the tree.** `icw_phasing` (validation, candidates, couple-level matches by side), `match_graph` (merged AutoCluster graph with observability: support = reported / observable), `prospects` (close matches not in the tree), `relationship_check` (expected vs observed cM for confirmed relatives). Sketch.
- **Store of record.** `tree_store` (SQLite: family tree and genetics with equal standing, GEDCOM in and out with 99.7% of nodes round-tripping, edits with `origin` and readable `tree_notes.md`, `tree_edits.json` versioned, the database itself rebuilt), `place_store` (places as an import step). Prototype. Gramps.app opens the exported GEDCOM; its Python API needs GTK and isn't used.
- **Views and exports.** `dnapainter_export` (DNA Painter backups and PNGs), `match_view` (match-centred chromosome browser and research report), `locus_view` (segment-locus view with pile-up check), `geoview`. Prototype; HTML files stay in `data/`. `serve.py` writes an index of `data/output` (plus the research notes, read-only) and serves it on 127.0.0.1 (the map views need a web server for OpenStreetMap tiles).
- **Places and records.** `places`, `gazetteer` (public), `geocode`, `volumes` / `riksarkivet`, `residences`, `stays` (MyHeritage's repeated residence entries as one stay per place and period; a rote or parish-only stay folds into an overlapping farm stay), `lifepath`, `geoview` (filterable map of events and records, linkable by URL; with `people.html` and `volumes.html` one set of linked views), `errata` (corrections beside the MyHeritage master). Tests: `tests/test_places.py`. Sketch; see Next steps 6.
- **Legacy.** `segments.ipynb` (2021 heatmap, too-short chromosome lengths; retire), `segment_placement.py` (empty, ignored placeholder).

## Side project: face avatars (`genealogy_avatars/`)

A pure-Python package, built in a claude.ai chat and in git since 60e7090 (usage: [README_avatars.md](README_avatars.md)). A family-specific sheet that hard-codes names stays private. It has:

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

1. **The contested paternity (README use case), written up.** A likelihood ratio for full vs half sisters from the second-cousin amounts (simulated or published cM distributions; siblings' totals are not independent), a hypothesis page weighing DNA and letters, and the copy test once one-to-many downloads for the close sister-line matches and a first cousin's segments separate the grandmother's two copies. Calibrate how many testers make it decisive (Ped-sim or msprime on the actual pedigree).
2. **Data.** Run the readers on the remaining archived exports; check chip overlap for the raw kits; recruit testers on each sister line and on the paternal cousins; a rerunnable manifest of the Drive archive (type, date, size, which reader).
3. **Store.** Let the pipeline read from `tree_store` instead of CSVs; model several names per person; check the exported GEDCOM in Gramps.app; segment-level edits (lineage overrides) through the store.
4. **Model gaps.** Genetic-map interpolation (bp to cM) and an interval tree as the shared interval engine; the X chromosome; sex-specific maps; pile-up masking in placement (the locus view shows where); endogamy; an exploratory per-copy match-space view (Jaccard on cM intervals, pile-ups masked).
5. **Case 2.** Linnea's unknown father, with the same tools and its own config (`FAMILY_CONFIG`).
6. **Places as dated assertions on Wikidata parish items.** Resolve by archive code (exact), then volume label, then name (names are ambiguous: "Ryr" is four parishes). Still to do: missing historical aliases on Wikidata (e.g. "Norra Ryr" for Lane-Ryr); county and diocese at an event's date; TORA for farms; review the gazetteer proposals (`data/gazetteer_todo.md`); apply `errata.py` person-level fixes in `gedcom_io`; collate stays and open the gap volumes `residences.py` lists; `volumes.py`, `gazetteer.py build` and `residences.py` as pipeline steps. Gazetteer reading errors: the long s (ſ) is read as f, as p, or beyond recognition together with other letters (Lafstad = Lasstad, Topfult/Topphult = Topshult, Siulfhulf = Sävshult; -hult names suffer most). Candidate checks, unvalidated: flag names where f→s before s/h/t gives an existing name in the parish; an edit-distance search against TORA or OSM names in the parish; a parish lookup that falls back to `ortho()` on a unique hit ("Grenna" needed an alias). Old f for v (Kalf-, Hof-) stays a hand rename, since a general rule would break names like Rolf. Open: whether `Källeryd/Utom` is the soldattorp at Hjulshult; `Gazetteer.coords()` claims a `within` fallback it doesn't have.
7. **Earlier ideas, not started.** Verify the unverified export formats with real samples; the triage and group UI; a friend's tool as a host for the engine.

Done since the first checkpoint (details in git history and PIPELINE.md): trio-plus-siblings HMM; the 2023 MyHeritage and FTDNA exports; the store of record (`tree_store`); validation against GEDmatch (the 2020 hand phasing is only images); ICW and AutoCluster readers; the GEDCOM reader seeds tree links and anchors.
