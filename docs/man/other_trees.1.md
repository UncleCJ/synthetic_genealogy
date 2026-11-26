# OTHER_TREES(1)

## NAME

other_trees.py — other people's trees that hold ours, as pointers to genealogists

## SYNOPSIS

    python3 other_trees.py
    python3 other_trees.py --wikitree

## DESCRIPTION

Reads the tree-tier citations in volumes(1)'s `volume_refs.csv` and lists
one row per tree: MyHeritage sites (keyed by the site token in the cited
URL, not by the "Web Site" title), WikiTree managers, and the shared trees
Geni and FamilySearch. Reasoning: `docs/records.md`, "Other trees".

With `[wikitree] profile` set in family.toml (the proband's own WikiTree
profile, e.g. `Example-1`), it links WikiTree profiles to the tree: walking
parents from that profile, then searching WikiTree for each direct ancestor
still unlinked (dead, or born over 100 years ago) and walking up from each
hit. Without `--wikitree` it reads cached answers only; with it, it asks
WikiTree's public API for what is not cached (about a second per call, a few
hundred calls on a first run).

It prints the number of trees per kind and of WikiTree links per way found.

## FILES

Reads the configured GEDCOM and `data/output/volume_refs.csv` (run volumes(1)
first). Writes `data/output/other_trees.csv` (columns `kind` myheritage,
wikitree or shared; `key` the site token or manager's WikiTree ID; `title`;
`people`, `ancestors`, `living` counts; `branches`; `youngest`, the youngest
person held, which places the keeper; `link`; `note`) and
`data/output/wikitree_links.csv` (`mh_id`, `label`, `kin`, `branch`,
`wikitree`, `how` seed, walk, search, conflict or ambiguous; `wt_birth`,
`managers`). WikiTree answers are cached in `data/cache/wikitree.json`.

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml` (and so its data folder).

## EXAMPLES

    python3 other_trees.py --wikitree   # first run: ask WikiTree
    python3 other_trees.py              # later: from the cache
