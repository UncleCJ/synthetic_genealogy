# ROWS(1)

## NAME

experiments/register_ocr/rows.py — the cited people's rows on the archive shelf: moves and remarks (sketch)

## SYNOPSIS

    python3 rows.py [ROOT] [--person MH:ID]

## DESCRIPTION

A sketch, unvalidated. For every citation in `data/output/volume_refs.csv`
whose page has line files on the shelf (ROOT, default `data/archive`;
shelf(1)), it finds the person's row and reads what stands in it, from the
text the shelf already holds: Vision's `ocr/<image>.vision.tsv`, TrOCR's
`.trocr.tsv` on the same boxes (preferred where present), and `cells.py`'s
`.cols.tsv` for the moved-in and moved-out cells where `read_pages` ran. It
reads no image and needs no model.

- **Columns.** Printed headers in the top quarter of the page name them:
  name, born, moved in, moved out, died, marriage, occupation, and the
  remark columns lyte, frejd, notes (anteckningar, anmärkningar), reading,
  communion (nattvard, bevistat husförhör), vaccination, military and
  guardian. A kind the page lacks comes from the volume's other pages
  where it stands on three or more. Each line goes to the nearest header
  by x: rough, so a remark can carry the wrong column name.
- **Rows.** Everyone cited on a page is placed at once. Each line in the
  name column goes to the cited person it fits best: the name fuzzily
  (each token's closest reading, a given name required) plus the birth
  read on the same height. A person keeps every line won at score 0.9 or
  more, so someone who left and came back has all their rows; otherwise
  their best line, marked unsure in `rows.tsv`. A row runs from halfway up
  to the previous name (a note starts at the top of the ruled cell, above
  the name) down to the next name line.
- **Moves.** Moved in/out text is parsed into year and parish (the
  gazetteer, abbreviations expanded) and checked against the parishes the
  tree cites the person in: known, new, within the book, abroad (America),
  unread, empty.
- **Remarks.** Any line in a remark column, and any line anywhere with a
  flagged word (sinnessjuk, svagsint, blind, dövstum, hospital, sjukhus,
  utskriven, intagen, fattighjon, inhyses, oäkta, hittebarn, dömd,
  fängelse, stöld, obefintlig, omyndig, …; fuzzy, so TrOCR's "vinnesjuk"
  counts). Lines in the name column count only when flagged; printed
  header text read into a row is dropped.

## FILES

- `data/output/moves_read.tsv`: mh_id, dir, year, place, text, volume,
  page, verdict (rows at score ≥ 0.9).
- `data/output/remarks_read.tsv`: mh_id, column, flag, text, alt (Vision's
  reading), volume, page, image (rows at score ≥ 0.9).
- `data/cache/rows/rows.tsv`: every citation tried, with score, the name
  as read, the headers found, moves and remarks, for checking the pass.

The Family view shows both files under a person's references as hints
(familyview.py's `shelf_hints`): read from the pages, never stored.

## OPTIONS

`--person MH:ID` prints that person's rows (moves and remarks) and
writes nothing.

## SEE ALSO

shelf(1), `experiments/register_ocr/README.md` (cells.py, htr.py),
docs/records.md (the Family view).
