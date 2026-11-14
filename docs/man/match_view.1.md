# MATCH_VIEW(1)

## NAME

match_view.py — a match-centred chromosome browser and research report, as one HTML file

## SYNOPSIS

    python3 match_view.py --entry NAME
    python3 match_view.py --focus "Erik Example" [--focus "Anna Example" ...] [--title T]
    python3 match_view.py --like REGEX [--title T]
    python3 match_view.py ... [--out FILE] [--md]
    python3 match_view.py --report NAME [--focus ... | --like REGEX] [--title T]
    python3 match_view.py --all-reports

## DESCRIPTION

Builds a report for a few DNA matches (the focus), from
`placed_segments.csv`, the phased painting and the AutoCluster runs. Per
sibling it paints both parental copies by grandparent, with the focus
matches' segments, triangulation candidates (overlap of at least half the
shorter segment, 7 cM or more), totals, shared-match neighbours, linked
tree persons, and the research entry's text. With a confirmed
`[[identity]]` in `family.toml` it adds a relation section (expected and
observed cM, odds, path variants, whether the placement fits the path);
without one, the indications. Both end with the ancestors involved as an
Ahnentafel list with record references.

The page is one self-contained file and makes no network requests. It names
matches, so it is private: it stays in `data/`.

Focus comes from `--focus` (repeatable, a match name), from `--like` (every
match whose name fits the regex, case-insensitive, added as a group), or
from the `people` of the research entry given with `--entry`.

## OPTIONS

`--entry` *NAME* — a research entry (`research/NAME.md`); its header's
`people` are the focus, its title the default title, its text the "Research
notes" section.

`--title` *T* — page title; default the entry's, else the names.

`--out` *FILE* — where to write; default `report_<title>.html` in the data
folder.

`--md` — also write the facts as compact Markdown beside the HTML (same
name, `.md`).

`--report` *NAME* — a kept report, `data/notes/reports/NAME.md`: a TOML
header (`title`, `focus`, `like`, `written`) between `+++` lines, then a
hand-written summary for an outside reader. Missing, it is created from
`--focus`/`--like` and you write the summary there. Existing, the facts are
regenerated and the summary kept. Writes `output/report_NAME.html` and the
`.md`.

`--all-reports` — regenerate every kept report.

## FILES

Reads `placed_segments.csv`, `placed_matches.csv`, the phased painting,
`volume_refs.csv` (record references; `[reports] hide_references` in
`family.toml` drops some), `research/NAME.md`. Writes the HTML (and `.md`)
under the data folder, and `data/notes/reports/NAME.md` when a kept report
is created. If the tree is missing the report still runs, without the
relation section.

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml` (and so its data folder).

## EXAMPLES

A report on one match:

    python3 match_view.py --focus "Erik Example" --title "Erik Example"

Everyone with one surname, as a group:

    python3 match_view.py --like '\bExempel\b'

Keep a report, then refresh it after new data:

    python3 match_view.py --report erik --focus "Erik Example"
    python3 match_view.py --all-reports

## SEE ALSO

locus_view(1), riksarkivet(1), `docs/genetics.md`, `docs/records.md`,
`research/README.md`
