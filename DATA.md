# Data folder and viewing the results

The data folder (`data/`, set by `data_dir` in `family.toml`) is private and
not versioned on the public line. It is split by what a file *is*:

| Folder | Holds | Written by code? | Back up? |
| --- | --- | --- | --- |
| `input/` | downloads as received: vendor exports (FTDNA, MyHeritage, GEDmatch pages), GEDCOM exports, raw genotype files, AutoCluster runs, DNA Painter backups | never | yes: it cannot be downloaded again later |
| `notes/` | files kept by hand: `errata.toml`, `plac_map.toml`, `research/` entries | only `research_log.py` (its INDEX.md) | yes |
| `store/` | `tree.sqlite` (rebuildable), `tree_edits.json` and `tree_notes.md` (the edits made in the store and their log: not rebuildable) | yes | the two text files, yes |
| `cache/` | answers from web services for private place strings | yes | no: refetched on demand |
| `output/` | everything the pipeline writes: views (HTML), reports (Markdown), tables, images, logs | yes | no: delete it and run `python3 pipeline.py` |

What to back up and where (a private cloud folder, kept current with
`python3 backup.py status`): WORKFLOW.md, "Backing up the private side".

Code does not need to know about the folders. `cfg["data_dir"] / "name"`
finds a file in whichever folder holds it, and a new file goes to `output/`
unless it is one of the known notes, store or cache files (`config.py`).
`family.toml` names files without a folder (`file = "export.ged"`).

New downloads go into `input/`; the next pipeline run picks them up through
`family.toml`. Public reference data (the gazetteer of places and its
caches) is not here but in `gazetteer/`, on the public line.

## Viewing the results without Claude

The views link to each other and the map views load OpenStreetMap tiles,
which the tile servers only serve to pages from a web server, not to files
opened directly. So:

```bash
python3 serve.py
```

writes `data/output/index.html` (every output with a one-line description)
and serves `data/output` at <http://127.0.0.1:8000>, on this machine only.
With Docker instead of a local Python (run `python3 serve.py --index` once
for the index page):

```bash
docker run --rm -p 127.0.0.1:8000:8000 -v "$PWD/data/output:/srv:ro" python:3.12-slim python -m http.server 8000 --directory /srv
```

Markdown reports open as formatted pages and CSV tables as sortable,
filterable tables (`?raw=1` gives the file itself). The pipeline log
follows a run while it goes: `output/pipeline_log.md` is the current or
latest run (it says which step is running), and every run keeps its own
file in `output/logs/`, so nothing is rotated or overwritten. A lock lets
only one pipeline run at a time.

Views take their state from the address, so links can be bookmarked or
shared between views, e.g. `geography.html#person=MH:I1,MH:I2&lines=1` or
`volumes.html#view=people&q=MH:I1` (see `geoview.py` for the full scheme).

## Another family's data

Everything family-specific comes from `family.toml` and `data/`. To try the
tools on another person's kits and tree, copy `family.example.toml` to a new
file pointing at another data folder and run with it:

```bash
FAMILY_CONFIG=other/family.toml python3 pipeline.py
```
