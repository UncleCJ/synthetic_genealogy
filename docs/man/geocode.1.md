# GEOCODE(1)

## NAME

geocode.py — coordinates for the gazetteer's places, each with its level and source

## SYNOPSIS

    python3 geocode.py [places] [--offline]
    python3 geocode.py show <regex>

## DESCRIPTION

**places** (the default) gives each gazetteer place a point, at the best
precision the sources allow, and records `lat`, `lon`, `geo_level` and
`geo_source` in `gazetteer/places.toml`:

| Level | Source | Uncertainty |
|---|---|---|
| farm | TORA, OpenStreetMap dwelling/farm/hamlet | ~0.3 km |
| village | TORA / OpenStreetMap village | ~1 km |
| parent | the place it lies `within` | ~2 km |
| parish | the parish's Wikidata point | ~6 km |
| town, region | OpenStreetMap town; county, state, country | 5 km to 300 km |

Per place: TORA by exact label, then OpenStreetMap inside a box around the
parish, then the place it lies within. A candidate must lie within 12 km
of the parish's point (same-named farms are common). Spelling variants and
abbreviated prefixes ("St." for Stora) are tried; a name that is only a
part of the written one gives village level at best. Generic names
("Sörgården") get no point of their own; the parish's is used at display
time. A place marked `checked`, or with `geo_source = "manual"`, is never
overwritten. Prints how many places have coordinates and the sources used.

**show** *regex* prints id, coordinates, level and source of the places
whose id matches.

The module also holds `locality()`, used by the life-path views for place
strings outside the gazetteer: town level at best, parts with digits or
street words dropped before anything is sent, answers cached privately.

## OPTIONS

`--offline` — use cached answers only; no requests.

## FILES

Reads and writes `gazetteer/places.toml`; reads `gazetteer/parishes.toml`.
Cache: `gazetteer/cache/geocode.json`.

## NETWORK

TORA by SPARQL, 40 names a query, one second apart. Nominatim at one
request a second, identified by User-Agent, results cached. Failures are
retried four times with growing pauses.

## ENVIRONMENT

None; the gazetteer is shared by all families.

## EXAMPLES

    python3 geocode.py places
    python3 geocode.py places --offline
    python3 geocode.py show "Exempelby/"

## BUGS

The docstring says lookups outside the gazetteer are cached privately in
`data/`; the code caches them where the caller passes (the life-path views
decide), and `places` writes `gazetteer/cache/geocode.json`, which is
public. `show` with no regex lists every place.

## SEE ALSO

gazetteer(1), places(1), `docs/records.md`, `docs/pipeline.md`
