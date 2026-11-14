# LOCUS_VIEW(1)

## NAME

locus_view.py — everyone who shares DNA at one place on one chromosome

## SYNOPSIS

    python3 locus_view.py --at CHROM:MB [--window MB] [--min-cm CM] [--out FILE]

## DESCRIPTION

Writes one self-contained HTML file for a locus: the donors (the siblings
and the mother) and the matches with segments overlapping a window around
the point.

Per donor it shows the grandparent copy each sibling carries there, and
every segment in the window packed under the copy it lies on and coloured
by grandparent. A segment shared end to end with another sibling (Jaccard
0.9 or more) is outlined. Curves join matches that are shared matches of
each other (from the AutoCluster graph). Above the tracks, the number of
segments covering the point is set against the donor's median over a 1 Mb
grid of the autosomes; three times the median or more is marked as a
possible pile-up. A table lists the matches in the window. Positions are
GRCh37 Mb.

The page makes no network requests. It names matches, so it is private and
written to `data/`.

## OPTIONS

`--at` *CHROM:MB* — required: chromosome 1–22 and position in Mb, e.g.
`2:236`.

`--window` *MB* — width of the window, centred on the point; default 20.

`--min-cm` *CM* — leave out shorter segments; default 7.

`--out` *FILE* — default `locus_chr<chrom>_<mb>Mb.html` in the data folder.

## FILES

Reads `placed_segments.csv`, the phased painting, the AutoCluster graph
(through `match_graph`), and `family.toml` (children, mother, identities,
grandparents). Writes the HTML only. Without a usable graph the page is
made without the links.

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml` (and so its data folder).

## EXAMPLES

    python3 locus_view.py --at 2:236
    python3 locus_view.py --at 15:75 --window 30 --min-cm 10 --out data/output/locus.html

## SEE ALSO

match_view(1), `docs/genetics.md`
