# RESIDENCES(1)

## NAME

residences.py — residence histories from household examinations, against the tree's own residence events

## SYNOPSIS

    python3 residences.py
    python3 residences.py <MH id> [<MH id> ...]

## DESCRIPTION

Turns each person's volume citations (volumes(1) rows) into record stays,
reads the tree's RESI events as documented stays (aggregated by
`stays.py`), and compares them. Only household examinations and parish
books count as residence evidence (series A I, A II, A II a, A II b); birth,
marriage, death and moving lists are events. A record stay's years are the
volume's years, so moves are only bracketed. Reasoning: `docs/records.md`,
"Residences and stays".

Per person it reports:

- **gap**: years between record stays, with the neighbouring volumes to open
  next (looked up at Riksarkivet; after the last volume of A I, the first of
  A II a), also from the last stay to the death year.
- **move**: between parishes, bracketed by the volume years, with documented
  stays that fall in the bracket.
- **not collated**: record stays no documented stay covers (same parish or
  unknown, overlapping years): candidates for a RESI event.

With no argument it writes the CSV and prints totals: people with volume
citations, gaps, bracketed moves, people with stays not yet collated. With
MH ids (`MH:I123`) it prints those people's timelines as text and writes
nothing.

## FILES

Reads what volumes(1) reads. Writes `data/output/residences.csv`
(columns `mh_id`, `label`, `kin`, `kind`, `start`, `end`, `parish`,
`place`, `detail`; kinds record, documented, gap, move, not collated).
Riksarkivet answers cached in `gazetteer/cache/riksarkivet.json`; the
volume lookups use the network on a cache miss.

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml` (and so its data folder).

## EXAMPLES

    python3 residences.py
    python3 residences.py MH:I123

## BUGS

Volumes with lettered numbers ("4c") get no next-volume suggestion.
Always runs volumes.run with Riksarkivet lookups on; there is no
`--no-riksarkivet`.

## SEE ALSO

volumes(1), store_query(1), tree_store(1), `docs/records.md`,
`docs/pipeline.md`
