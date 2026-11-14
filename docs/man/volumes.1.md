# VOLUMES(1)

## NAME

volumes.py — the record volumes the tree's citations point at, and who is on the pages

## SYNOPSIS

    python3 volumes.py [--wikidata] [--no-riksarkivet]
    python3 volumes.py [--wikidata] [--no-riksarkivet] farm <farm name regex>

## DESCRIPTION

Reduces every citation in the tree to one row with a tier: `ra-full`
(Riksarkivet citation, or an Arkiv Digital reference with its volume),
`ra-link` (a viewer URL only), `mh-record` (MyHeritage household
examination), `mh-index` (other MyHeritage collections), `tree` (other
trees and sites), `plac-only` (a place and no citation). Rows are keyed by
volume (parish, series, volume); each cited person is classed against the
proband (ancestor, relative with branch, spouse of a relative, unlinked).
Parishes and farms are resolved through the gazetteer; errata are applied
last. How references and volumes are read: `docs/records.md`, "References
and volumes".

With no command it writes the files below and prints counts: rows per
tier, volumes and parishes, farms placed, errata applied, and Riksarkivet
links in image series with no full citation to name their volume.

**farm** *regex* prints one farm (case-insensitive match) across volumes:
per volume and page, who is on it and how they are related. Writes nothing.

## OPTIONS

`--wikidata` — also resolve parishes cited only by name on Wikidata
(slow; places.py).

`--no-riksarkivet` — skip Riksarkivet volume lookups. Without it, volumes
are looked up at Riksarkivet over the network, cached.

Parishes cited only as places can be named in `family.toml`:
`[volumes] parishes = ["..."]`.

## FILES

Reads the GEDCOM and `errata.toml` named by `family.toml`, the gazetteer
(`gazetteer/parishes.toml`, `places.toml`, `data/plac_map.toml`), and the
caches in `gazetteer/cache/`.

Writes to `data/output/`: `volume_refs.csv`, `archives.html` (the Archives
view), `errata_report.md`.

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml` (and so its data folder).

## EXAMPLES

    python3 volumes.py --no-riksarkivet
    python3 volumes.py farm "Exempelby|Exempeltorp"

## BUGS

Any `--` word is dropped before the command is read, so `--typo` is
ignored silently. Not handled: Sveriges dödbok; a volume suffix as in
"Exempel_AIIa3-296" (kept as written).

## SEE ALSO

places(1), gazetteer(1), residences(1), errata(5), `docs/records.md`,
`docs/pipeline.md`
