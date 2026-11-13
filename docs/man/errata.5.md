# ERRATA(5)

## NAME

errata.toml — corrections and notes kept beside the MyHeritage tree

## SYNOPSIS

    data/notes/errata.toml        (private; TOML)
    examples/errata.example.toml  (the format, public)

## DESCRIPTION

Two kinds of entry, any number of each, in any order.

    [[fix]]                         [[note]]
    key    = "<key>"                key  = "<key>"
    field  = "<field>"              text = "<free text>"
    was    = "<export says>"        date = "YYYY-MM-DD"
    now    = "<should say>"
    source = "<how you know>"
    date   = "YYYY-MM-DD"

`was` is what the export says today (`""` for missing). It makes the entry
self-checking: once MyHeritage changes, the entry knows.

## KEYS

Something that survives a re-export:

| Key | Names | Find it with |
|---|---|---|
| `mh:<itemId>` | a MyHeritage record (household examination etc.) | Archives view, the record link |
| `bild:<imageid>_<NNNNN>` | a Riksarkivet image, e.g. `bild:C0012345_00042` | the citation's bildid |
| `volume:<refcode>` | a volume, e.g. `volume:SE/XXXA/00000/A I/20` | Archives view |
| `person:<MH:I123>` | a person | `store_query.py find` |
| `place:<Parish/Name>` | a gazetteer place | Geography view |
| `plac:<raw string>` | one place string as written in the tree | `store_query.py sql` on `event.place` |

## FIELDS

On citation rows (keys `mh:`, `bild:`, `volume:`, `place:`, `plac:`):
`page`, `row`, `farm`, `series`, `vol`, `years`, `parish`, `place_id`.

On persons: `birth`, `death`, as GEDCOM dates (`12 MAR 1890`,
`ABT OCT 2020`, `BEF 1900`). Applied by the family lens; other person
facts are keyed but not applied yet.

## STATUS

Written to `data/output/errata_report.md` by the volumes step of each run:

- **applied** — the export still says `was`; the fix is used.
- **retired** — the export says `now`; delete the entry.
- **conflict** — the export says something else; look again.
- **orphan** — nothing has the key any more.
- **attached** — a note found its key.

## EXAMPLES

A page number the index got wrong:

    [[fix]]
    key = "mh:12345678"
    field = "page"
    was = "35"
    now = "36"
    source = "Riksarkivet image checked"
    date = "2026-11-14"

A death not in the tree yet:

    [[fix]]
    key = "person:MH:I123"
    field = "death"
    was = ""
    now = "ABT OCT 2020"
    source = "death notice seen; month approximate"
    date = "2026-11-14"

What the export says now, before writing `was`:

    python3 store_query.py sql "select tag, date, place from event where owner='MH:I123' and tag in ('BIRT','DEAT')"

Entries that can go:

    grep -A3 '^## retired' data/output/errata_report.md

## SEE ALSO

tree-edits(7), `errata.py` (the code and its docstring), `data/notes/plac_map.toml`
(place strings the gazetteer rules misread)
