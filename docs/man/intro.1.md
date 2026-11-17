# INTRO(1)

## NAME

intro — the tools run by hand, one page each

## DESCRIPTION

Every page here is for a command a person runs. The pipeline's own steps
(painter … research) are described in `docs/pipeline.md`; the modules by
layer in `docs/architecture.md`.

| Page | Tool | What for |
|---|---|---|
| **Running and browsing** |||
| pipeline(1) | `pipeline.py` | the genetic chain, step by step, with a log |
| serve(1) | `serve.py` | browse `data/output` and the notes in a browser |
| backup(1) | `backup.py` | hand-kept private files: status and snapshots |
| **Research and views** |||
| research_log(1) | `research_log.py` | research entries: new, index, look up by position |
| match_view(1) | `match_view.py` | one match or a group, with kept reports |
| locus_view(1) | `locus_view.py` | everything at one chromosome position |
| **Editing the tree** (start at tree-edits(7)) |||
| tree_store(1) | `tree_store.py` | the store: imports, rebuilds, additions |
| store_query(1) | `store_query.py` | read-only questions to the store |
| errata(5) | `data/notes/errata.toml` | corrections and remarks on the master tree |
| **Records and places** |||
| places(1) | `places.py` | archive codes to Wikidata parishes |
| riksarkivet(1) | `riksarkivet.py` | one archive volume: years, pages, links |
| volumes(1) | `volumes.py` | citations to volumes, pages and farms |
| gazetteer(1) | `gazetteer.py` | the public place list: build, show |
| geocode(1) | `geocode.py` | coordinates for gazetteer places |
| maplayers(1) | `maplayers.py` | old maps and aerial photos as layers in the geography view |
| residences(1) | `residences.py` | stays, gaps and moves from citations |
| textfix(1) | `textfix.py` | repair damaged å/ä/ö: text, stdin or clipboard |
| fetch(1) | `experiments/register_ocr/fetch.py` | archive page images, cached (proof of concept) |
| shelf(1) | `experiments/register_ocr/shelf.py` | local shelf of cited volumes: covers, cited and index pages (sketch) |
| sweep(1) | `experiments/register_ocr/sweep.py` | a place's pages in whole volumes, from registers and page heads, read locally (sketch) |

Sections as in Unix: (1) commands, (5) file formats, (7) overviews.

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml`; most tools honour it.

## SEE ALSO

tree-edits(7), `docs/pipeline.md`, `docs/data.md`
