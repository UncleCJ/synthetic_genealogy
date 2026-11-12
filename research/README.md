# Research log

A genealogist's working memory: what we are wondering, suspecting and have
settled, kept apart from computed output. `revelations.md` and the CSVs in
`data/` are regenerated on every run. Entries here are judgements: they
persist, change status, and cite the computed output rather than repeat it.

One Markdown file per entry, named `<id>.md`. A TOML header between `+++`
lines, then free prose. `python3 research_log.py` checks every entry and
writes `INDEX.md`. The entries are private (they name living relatives);
this README and the tool are public.

## Header

```toml
+++
id = "q-anna-relation"            # = file name; prefix by kind (q-, h-, s-, f-, n-)
kind = "question"                  # question | hypothesis | segment | finding | note
title = "How is Anna related to us?"
status = "open"                    # see below
created = 2026-11-08
updated = 2026-11-08
confidence = "low"                 # hypotheses and findings: low | medium | high
people = ["Anna Example"]         # donors, matches or ancestors, as written in sources
lineage = ["MF"]                   # lineage codes involved (F/M paths, e.g. "MFM")
related = ["h-erik-double-cousin"]  # other entry ids
evidence = ["data/placed_matches.csv", "assertion:dnapainter:...:529"]  # files, assertion ids, URLs

# segments of interest, one inline table each (bp, GRCh37)
segments = [
  { subject = "anna", chrom = "3", start = 100000, end = 37000000, match = "Erik Example", platform = "FTDNA" },
]
+++
```

Only `id`, `kind`, `title`, `status`, `created` are required.

## Kinds and statuses

| kind | means | statuses |
|---|---|---|
| question | something we want to know | open, parked, answered |
| hypothesis | a claim we suspect, to be tested | open, supported, refuted, parked |
| segment | a stretch of DNA worth remembering (odd, conflicting, key) | open, explained, parked |
| finding | settled, with its evidence; the log's long-term memory | settled, retracted |
| note | anything else (method, source quirk, contact) | open, done |

## Body

Free prose. Suggested sections, all optional:

- **Context**: why this matters.
- **Evidence**: for and against, citing files, assertion ids, segments.
- **Next**: what would settle it (a test to ask for, a record to read).
- **Log**: dated one-liners, newest last, e.g. `- 2026-11-08: Erik anchor corrected chr15 labels.`

## Tool

```bash
python3 research_log.py                  # check entries, write research/INDEX.md
python3 research_log.py new question "How is Anna related to us?"
python3 research_log.py at 3 30000000    # entries with a segment covering chr3:30 Mb
```
