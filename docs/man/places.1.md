# PLACES(1)

## NAME

places.py — parish items on Wikidata: archive codes, volume labels, names, history

## SYNOPSIS

    python3 places.py [codes]
    python3 places.py volumes
    python3 places.py history <Q-id>
    python3 places.py name <place name words>

## DESCRIPTION

Resolves the place evidence in the tree's GEDCOM to Wikidata parish items
(socken, församling, distrikt) and reads a parish's history. How parishes
are modelled over time: `docs/records.md`, "Parishes, congregations and
towns". Wikidata is asked through the action API, one request a second,
with the throttle's `Retry-After` honoured; every answer is cached.

**codes** (the default) lists the Riksarkivet archive codes cited in the
tree with a count, the archive's name, and the Wikidata items carrying the
code (P5324). A code can sit on several items; "no item" means none.

**volumes** lists the vendor volume labels cited (MyHeritage household
examinations: parish, series, volume, years) with a count. Names only: no
Wikidata lookup.

**history** *Q-id* prints one parish item: label, kind, aliases, archive
and ATA codes, years it existed, and the items that replaced it.

**name** *words* lists candidate parishes for a written name. Abbreviations
(`N.`, `S.`, `V.`, `Ö.`, `W.`) are expanded as guesses, never answers; a
name that is no alias ("Norra Exempel") falls back to parishes ending in
its last word.

Sketch, unvalidated. Not handled: county, härad and diocese at a date,
farm-level places, TORA.

## FILES

Reads the GEDCOM named in `family.toml` (`codes`, `volumes` only).
Reads and writes `gazetteer/cache/wikidata.json` (public). Prints to
standard output; writes nothing else.

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml` (and so its GEDCOM).

## EXAMPLES

    python3 places.py codes
    python3 places.py history Q123
    python3 places.py name "Norra Exempelby"

## BUGS

`history` with no *Q-id* fails with an index error. Other words than the
four commands print the module docstring.

## SEE ALSO

volumes(1), gazetteer(1), geocode(1), `docs/records.md`, `docs/pipeline.md`
