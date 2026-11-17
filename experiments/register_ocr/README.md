# Register OCR (proof of concept, unvalidated)

"Are they there?" for a few pages of a Riksarkivet household examination,
with no cloud AI: Tesseract for print, Apple Vision (on-device, macOS) for
handwriting, numpy for the form's grid. Tried on one Västergötland volume
(pre-printed Tullberg forms, 1890s) only.

- `fetch.py` (man page: `docs/man/fetch.1.md`): IIIF images or pixel regions, cached on disk, one per second.
  The image server is IIIF level 1 (pixel regions, `w,` sizes; no `pct:`)
  and refuses requests without the viewer as Referer. Bulk use waits on
  Riksarkivet's terms.
- `vision.swift`: text lines with boxes and three candidates
  (`swiftc -O vision.swift -o vision`; about 0.4 s per page).
- `find.py`: scans a few images for a name (fuzzy), with the year column
  as a squinted tie-breaker; prints each image's page number and farm.
- `grid.py`, `extract.py`: frame rules, 30 evenly spaced rows, the year
  column; which rows are filled; name and year crops for review.

What worked on that volume:

| Task | Reader | Result |
|---|---|---|
| Printed page number and farm heading, top strip only (26 KB) | Vision | 9 of 12 images; page = image − 16 throughout, gaps interpolated |
| Farm index ("Register", front of volume) | Vision | page numbers 19 of 30 exact; farm names rough, need fuzzy match against the parish's farms |
| Filled rows | ink in the grid | 10 of 10, no false rows |
| Names in a household | Vision + fuzzy | 5 of 5 found, the right row first |
| Two-digit birth years | Vision | about 6 of 10; Tesseract none |

The year reader is the weak part: Vision merges year and birthplace into
one line and reads digits as letters. Crops of the year cell are the
fallback, for a person to read.

## Riksarkivet's handwriting model (TrOCR)

Vision finds lines and reads print, page numbers and header years, but
rarely names in older hands. Riksarkivet's open model
`Riksarkivet/trocr-base-handwritten-hist-swe-2` (Hugging Face, runs
locally, about 50 s a page on Apple MPS) reads them. Set up once, in a
venv of its own (it needs `transformers<5`):

```bash
python3 -m venv ~/.cache/sg-htr-venv
~/.cache/sg-htr-venv/bin/pip install torch "transformers<5" pillow numpy
```

After the first download, run with `HF_HUB_OFFLINE=1`.

- `htr.py ROOT [--follow]`: re-reads the shelf's Vision line boxes with
  TrOCR (`docs/man/shelf.1.md`).
- `cells.py IMG OUT [--vision TSV] [--cols name,in,out]`: one reader for
  ruled forms. Printed headers in the page's Vision lines name the columns
  (name, moved in, moved out, born, died, age; loosely, Vision misreads
  print too), the form's rules (`grid.py`) give their edges; without
  headers, the widest gap on the left page is the name column and the
  next the age. Rows are text lines from the ink profile of the name
  column, tall bands split at ink valleys; each cell read with TrOCR.
  Output: name-cell box, then `column=text` per column.

On six cited pages with printed migration headers (2026-11-17): on the
1880s–90s household-examination forms the cited person's row was found
(name score 0.66–0.88) and the moved-in and moved-out cells read as
parish, year and date, rough but legible ("V. Tolstad 1873", "Sct Per
9. 1/2", "fol. 28"). On the församlingsböcker (1906–1931) the name column
has no printed header and the fallback band caught the birth data, so
the row was not found; the migration cells there read empty or as header
text. Next: the name column of the församlingsbok by its rules, the row
from MyHeritage's row number, and column positions as the volume's
median.

On 12 known death-book entries (ruled print forms, 1850s–1890s, seven
parishes): Vision alone found no names; TrOCR on Vision's boxes (as `htr.py`) found 5–6; `cells.py` found
9 of 12 names (score ≥ 0.8), with the age on the same row for 6. Free-form
ledgers without columns fail. Match on name and age together: a namesake
on the same page once scored higher. The scoring and tree-matching
scripts hold names and stay private (`data/cache/death_pass/`).

Which reader for what: Vision for every page (cheap: page numbers,
headings, farm index, year headers); TrOCR only on the cells of pages a
question points to (slow, but reads names).
