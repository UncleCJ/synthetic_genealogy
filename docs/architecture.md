# Architecture

How the modules fit together. The ideas behind them: [concepts.md](concepts.md).
Each step in run order, with an anonymised run: [pipeline.md](pipeline.md).

```
  received (data/input/)            kept by hand (data/notes/, family.toml)
  exports, GEDCOM, raw kits,        errata, place map, anchors, identities,
  AutoCluster, DNA Painter          research entries, store edits
            \                          /
             v                        v
         readers  (ftdna_io, myheritage_io, gedcom_io, icw_io, ...)
            |                                   |
            v                                   v
   genetic chain                          records chain
   anchors -> phasing -> placement        places -> gazetteer -> volumes
   -> consistency -> shared matches       -> residences / stays
   -> exports, graph, prospects
            \                                   /
             v                                 v
        rebuilt (data/output/, data/cache/)  <---->  tree store (tree.sqlite)
        reports, tables, paintings, views
                         |
                         v
          serve.py (browse locally) · backup.py snapshot (read elsewhere)
```

The genetics steps pass their tables through the store (`outputs.py`):
each step writes its tables there (and a CSV in `data/output/` as the
readable view), the next reads them from there, and the store's `artifact`
table says which step wrote what and when (`python3 outputs.py`). Lineage
and descent claims from every source sit in one `assertion` table. The
tables are kept as reading their CSV gives them, so the move changed no
result. Hand-kept state stays in files and is never only in the store. The
tree, places and DNA tables of `tree_store` are imported from the GEDCOM,
the gazetteer and the pipeline's tables; the records tools don't go
through the store yet.

All modules are flat in the repository root. Module docstrings carry the
details and the caveats; the code is readable sketches, unvalidated unless
a check says so.

## Setup and shared helpers

- `config.py`: loads `family.toml` (or `FAMILY_CONFIG`) and resolves file
  names into the data folder's layers.
- `kits.py`: builds kit dicts (subject, sex, platform, date, segments, keys)
  from the segment exports listed in `family.toml`, including partial
  selections and earlier exports.
- `family_filter.py`: recognises the family's own kits in match lists and
  paintings, by whole name or kit.
- `textfix.py`: repairs Swedish letters damaged by vendor exports
  (mojibake, HTML entities).
- `intervals.py`: one interval vocabulary for both halves: overlap, union,
  Jaccard and bins on bp; a genetic map for bp↔cM (read from a HapMap,
  Bherer or PLINK file, flat 1 cM/Mb without one); fuzzy year spans from
  GEDCOM dates.
- `identity.py`: the keys rows are joined on (one name key, MyHeritage
  kit ids, the tree's MH ids) and how strong each is.
- `lineage.py`: lineage codes and Ahnentafel numbers, common prefixes, the
  grandparent-couple split.
- `assertions.py`: lineage and descent claims from every source in one
  shape, with an independence group so one match can count once.
- `outputs.py`: the pipeline's tables through the store: `write` (store
  table plus CSV view), `read`, and which step wrote what.

## Readers

- `references.py`: archive references in free text, one shape from named
  readers (Riksarkivet citations, also led by the code; Arkiv Digital;
  MyHeritage book labels; image links). `volumes` reads them in source
  citations, notes, addresses and event values.
- `ftdna_io.py`: FamilyTreeDNA Family Finder match lists and chromosome
  browser exports.
- `myheritage_io.py`: MyHeritage shared-segment exports, bulk and the
  selective one-to-many captures, triangulated rows kept apart.
- `dnapainter_io.py`: DNA Painter profile backups as segment-origin
  assertions.
- `gedmatch_io.py`: saved GEDmatch one-to-one pages, used to check the
  phasing.
- `icw_io.py`: shared-match evidence (AutoCluster CSVs, Gephi files, FTDNA
  in-common-with lists) as one edge table.
- `gedcom_io.py`: a GEDCOM 5.5.1 tree (Gramps or raw MyHeritage) with
  lineage codes, kinship over all paths (identical twins included) and
  confirmed identity links. People with no family link to the proband
  (hypothesis islands) are left out unless `[gedcom] keep_unlinked`.
- `gedcom_audit.py`: diff two tree exports; look for redundancy in one.

## Genetics

- `documented_anchors.py`: documented relatives and tree links as weighted
  lineage assertions.
- `visual_phasing.py`: the inheritance-vector HMM over three siblings, with
  a tested mother in the emissions and sibling-shared segments as soft
  evidence.
- `phasing_labels.py`: names the anonymous sides and grandparents from the
  anchors, judged leave-one-out.
- `match_placement.py`: places children's and the mother's match segments
  on grandparent copies (including the containment rule for the parent
  side, and the side from which phased siblings share a segment where
  the mother's list is silent), reading each child's copy model where it
  has one (`[placement] method`, default) and the painting otherwise;
  without a painting, the copy models alone, with sides from relatives at
  a known path who share the segment (`[[placement.relatives]]`).
- `revelations.py`: runs the placement over every export and writes the
  placed tables and the report.
- `sibling_consistency.py`: segments siblings share with a match must sit
  on the same copy; corrects short blocks.
- `icw_phasing.py`: shared-match votes against the segment placement;
  couple-level matches by side.
- `match_graph.py`: one merged shared-match graph from several runs, with
  support as reported / observable.
- `copy_model.py`: the copy model (round 2, first version): per tester, a
  belief along each copy about which ancestor it came from, to great-
  grandparent depth, from lineage claims (and, for phased siblings, the
  phasing's copy labels); leave-one-out verdicts per claim; match
  segments placed through it (`place`), compared with today's placement in
  `copy_model_placement.md`. Runs beside the painting, not instead of it.
- `deep_labels.py`: the copy model's great-grandparent labels read back
  from its stored tables (fits nothing): cM per great-grandparent by band
  (sure, likely, leaning), the claims naming each with their verdicts and
  joins, the deep claims it reads against (and whether they differ already
  at the grandparent), one chromosome in detail (`--chrom`), and a deep
  painting per tester (`--png`); the name-joined matches on deep paths
  to confirm by hand first (`--confirm`), with how their segments read.
- `grandparent_copies.py`: recursive deduction, first step: splits one
  grandparent's own two copies along the siblings' copy from her, from
  where her other descendants' segments end (her crossovers) and from
  relatives through her mother; the copy and sister tests as mean
  posteriors; `copy_test` reads each relative held out, with a
  permutation p-value (`--real <code> [--use-p] [--joint]`);
  `posterior_joint` reads her copy and each child line in one chain,
  absence included (an option, not the default); `--others` lists the
  matches no group explains, by which of her copies they sit on (whom to
  ask next). Checked on the simulator only (`simulate.grandmother`).
- `prospects.py`: close matches the tree doesn't explain yet.
- `relationship_check.py`: expected versus observed cM for confirmed
  relatives (identities may sit `down` generations below a tree person),
  and WATO-style odds per relationship from simulated distributions
  (`simulate.relationship_cm`, cached in `data/cache/`).

## Places and records

- `places.py`: resolves the GEDCOM's place evidence to Wikidata parishes
  (by archive code, volume label, then name).
- `gazetteer.py`: the public gazetteer of parishes and farms
  ([gazetteer/README.md](../gazetteer/README.md)), its build and variant
  proposals, and the one resolver of whole place strings
  (`plac_parts`, `explain_plac`) that the store, the map and
  `places_rules` share. A family whose parishes are not in it yet needs
  `gazetteer.py build --wikidata` once, or its places get no coordinates.
- `parish_names.py`: every Swedish parish name from Wikidata
  (`gazetteer/parish_names.tsv`), indexed by the forms place strings use
  (suffix and genitive dropped, a town's congregation without its town,
  "Ö." for Östra, lost å/ä/ö), narrowed by a written county; towns and
  modern kommuner told apart from parishes. `volumes.normalise` reads
  parishes through it when the family's citations don't name them.
- `place_hierarchy.py`: a place string shown with its whole hierarchy
  (detail, parish, town or kommun, landskap, län, a country other than
  Sweden), the levels it leaves out filled from what the tree's other
  strings say (two thirds of the votes), county letters, the parish list
  and län that lie in one landskap. Used by the geography view.
- `geocode.py`: coordinates for the gazetteer's places, at whatever
  precision the sources allow.
- `riksarkivet.py`: volume facts by reference code through Riksarkivet's
  open OAI-PMH service, read from each archive's whole inventory (one
  request): years, content note, page span, image series and count, the
  volume's catalogue (NAD) page; codes damaged in copying resolved
  against the inventory; free Riksarkivet links for citations, with the
  image a page is likely on when only the page is known.
- `volumes.py`: the research as it sits in the record volumes: parish
  books, pages, farms. Page strips run over the volume's own page span
  where Riksarkivet gives it, else to the highest cited page.
- `residences.py`: residence histories against the volumes, with the gap
  years and the volumes that would close them.
- `stays.py`: repeated residence entries aggregated into stays.
- `errata.py`: corrections kept beside the master tree, checked each run.

## Store

- `tree_store.py`: SQLite store for the tree and the genetics with equal
  standing; GEDCOM in and out; edits with origin, a readable log, and
  rebuild by replaying the edits.
- `place_store.py`: imports the gazetteer into the store and links events
  to places; towns and regions outside it are looked up online, cached per
  family in `cache/geocode_private.json` (`GEOCODE_OFFLINE=1`: the cache
  alone).
- `store_query.py`: quick read-only questions to the store (`find <name>`,
  `person <name|id>` with parents, spouses, children and kits, `sql`).

## Views and exports

- `dnapainter_export.py`: the computed painting back as DNA Painter
  backups and PNGs, each block with its support.
- `match_view.py`: a match-centred chromosome browser and research report,
  with or without a research entry: for a confirmed identity, each tester's
  relationship, expected and observed cM, odds and whether the placement
  fits the path; without one, the indications (odds, placement, shared
  matches, namesakes in the tree, entries naming the match); then the
  ancestors involved as an Ahnentafel list with their unique record
  references (volume codes where Riksarkivet confirmed them; sources
  matching `[reports] hide_references` left out). `--md` writes the facts as compact Markdown; a kept report
  (`--report NAME`, `data/notes/reports/NAME.md`) adds a summary for an
  outside reader, written once, and regenerates with `--all-reports`.
- `locus_view.py`: everyone in the family who shares DNA at one locus,
  with a pile-up check.
- `edges.py`: where things change along a chromosome, as terse text:
  siblings' crossovers, the copy model's changes (ancestral crossover
  edges among them), and clusters of segment ends with what explains
  them; `--summary` ranks the unexplained ones genome-wide.
- `geoview.py`: the filterable map of events and records
  (`geography.html`); with the archives view (`archives.html`, written by
  `volumes.py`) one pair of linked views whose state lives in the address
  bar.
- `places_rules.py`: the place-recognition rules as a page
  (`places_rules.html`): every normalisation with live examples, then the
  family's hand rules and which rule resolved each place string in the tree.
  `places_rules.py trace <regex>` prints how matching place strings and
  citations are read by both parsers (volumes and gazetteer), for
  troubleshooting.
- `showcase.py`: pseudonymised copies of the views and the README's
  screenshots, with a check for names and ids.

## Running it and the private side

- `pipeline.py`: runs the chain in order (smoke tests first) and logs each
  step to `data/output/pipeline_log.md`, one file per run in
  `data/output/logs/`.
- `serve.py`: an index of `data/output` (plus the research notes,
  read-only), served on 127.0.0.1 ([data.md](data.md)).
- `backup.py`: `status` / `mark` for the hand-kept files, `snapshot` for a
  dated zip ([privacy-workflow.md](privacy-workflow.md)).
- `research_log.py`: checks research entries, writes the index, creates
  and looks up entries ([schema](../research/README.md)).
- `hooks/pre-push`: refuses to push private commits from git; jj has its
  own guard.
- `simulate.py`: drops DNA through a known pedigree and applies vendor-style
  detection (threshold, noisy ends, false segments), keeping the truth; the
  scenarios the tests and later the models are checked against.
- `baseline.py`: freezes the output tables and diffs a later run against
  them, so a refactor that should change nothing can show that it doesn't.
- `tests/`: unit tests on synthetic data only, so they run without private
  files (and in CI).
