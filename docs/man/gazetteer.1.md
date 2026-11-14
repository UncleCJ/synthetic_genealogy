# GAZETTEER(1)

## NAME

gazetteer.py — the curated places file: seed it from the tree, look entries up

## SYNOPSIS

    python3 gazetteer.py [build] [--wikidata]
    python3 gazetteer.py show <regex>

## DESCRIPTION

The gazetteer holds the parishes, villages, farms and crofts the research
touches, as stable entities with spelling variants, apart from the tree.
MyHeritage stays master: its place strings are never edited, only resolved
to gazetteer entries on every run. How: `docs/records.md`, "Reading place
strings" and "Parishes, congregations and towns".

**build** (the default) reads the tree's rows (as volumes(1) does), adds
parishes and places of record, and fills empty fields. It never overwrites
or deletes. It repeats up to three passes until the files stop changing,
then saves both TOML files and writes the to-do list: looser matches
proposed as variants, unresolved strings, unknown parishes. Accept a
proposal by adding the variant to the entry. Modern addresses are not
added to the public file. Set `checked = true` on an entry once looked at.

**show** *regex* prints the places whose id or variants match, and the
parishes whose name matches, with their fields.

Place ids are `Parish/Name`; rename by adding the old name as a variant.
One odd string is fixed in `data/plac_map.toml` (raw string to place id).

## OPTIONS

`--wikidata` — online: also ask Riksarkivet for a new parish's archive
code, then Wikidata for its item and coordinates (places.py; cached).
Without it no requests are made.

## FILES

Reads and writes `gazetteer/parishes.toml` and `gazetteer/places.toml`
(public). Reads `data/plac_map.toml` (private) and the GEDCOM from
`family.toml`. Writes `data/output/gazetteer_todo.md`. Answers cached in
`gazetteer/cache/` (public).

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml` (the tree and the private
files; the public gazetteer is shared).

## EXAMPLES

    python3 gazetteer.py build
    python3 gazetteer.py build --wikidata
    python3 gazetteer.py show Exempelby

## SEE ALSO

geocode(1), places(1), volumes(1), `docs/records.md`, `docs/pipeline.md`
