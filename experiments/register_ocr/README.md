# Register OCR (proof of concept, unvalidated)

"Are they there?" for a few pages of a Riksarkivet household examination,
with no cloud AI: Tesseract for print, Apple Vision (on-device, macOS) for
handwriting, numpy for the form's grid. Tried on one Västergötland volume
(pre-printed Tullberg forms, 1890s) only.

- `fetch.py`: IIIF images or pixel regions, cached on disk, one per second.
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
