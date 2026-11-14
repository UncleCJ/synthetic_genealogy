# RIKSARKIVET(1)

## NAME

riksarkivet.py — look up a church-archive volume or parish archive at Riksarkivet

## SYNOPSIS

    python3 riksarkivet.py "SE/XXXA/00000/A I/1" [...]
    python3 riksarkivet.py <parish name> [...]

## DESCRIPTION

Each argument is looked up and printed; arguments starting with `SE/` are
reference codes, anything else a parish name.

A **reference code** (archive, series, volume: `SE/XXXA/00000/A I/1`) prints
the volume as JSON: `code`, `years`, `note`, `images` (the image series id),
`viewer` (the sok.riksarkivet.se image viewer), `manifest` (IIIF), `nad`
(the catalogue page) and `pages` (the page span read from the note, e.g.
`1-300`, with a unit when it is not pages). A volume Riksarkivet does not
have prints `null`. If the code differs from a real one only as copying
damages it (spaces, case, I/l/1, O/0), the one volume that fits is printed.

A **parish name** prints the reference codes of the archives captioned
"<parish> kyrkoarkiv", found through the open search API. Several codes mean
several parishes of that name.

Both use Riksarkivet's open services (OAI-PMH and the search API, no key).
Reading an archive's inventory may take a while. Requests are paced and
retried; a service that stays unreachable raises an error.

Series follow the usual kyrkoarkiv scheme (`A I` husförhörslängd, `C`
födelse- och dopbok, ...); some archives deviate. Tested on a handful of
codes from two provinces only.

The module is also used by the pipeline and the reports (links to volumes
and images); how it works is in `docs/records.md`, "References and volumes".

## FILES

The command line keeps no cache: every run asks Riksarkivet. Pipeline and
report code use `Riksarkivet(cache)`, which keeps answers in
`gazetteer/cache/riksarkivet.json` (public) and archive inventories beside
it as `*_inventory.json` (not committed).

## ENVIRONMENT

None. Reference codes opened in a browser need a captcha: the links are for
people, never for lookups.

## EXAMPLES

    python3 riksarkivet.py "SE/XXXA/00000/A I/1"
    python3 riksarkivet.py Exempelby

## SEE ALSO

fetch(1), match_view(1), `docs/records.md`
