# SWEEP(1)

## NAME

experiments/register_ocr/sweep.py — find a place's pages in whole volumes, then read them (sketch, unvalidated)

## SYNOPSIS

    PY=~/.cache/sg-htr-venv/bin/python; export HF_HUB_OFFLINE=1
    $PY sweep.py register TAG ID... --names "Name,Variant" [--width 2600] [--floor-gb 5]
    $PY sweep.py locate TAG ID... --names "Name,Variant" [--frac 0.5] [--tries 12]
    $PY sweep.py heads TAG ID... --names "Name,Variant" [--step 3] [--floor-gb 5]
    $PY sweep.py pages TAG [--pad 1] [--width 2600] [--floor-gb 5]
    python3 sweep.py report TAG [--pad 1]

## DESCRIPTION

For a local history: which pages of a parish's household examinations
and parish books concern a few named places. Volumes are Riksarkivet
image-series ids. Everything is read on this machine: Apple Vision finds
the lines, Riksarkivet's TrOCR model reads those Vision is unsure of
(handwriting); Vision's text is kept for confident lines (print).

**register** reads a volume's unnumbered front images whole (the
parish books' "Register. Byar och särskildt benämnda fastigheter"),
fuzzily matches each short line against the names, and takes the folio
numbers beside it (boxes to the right within the name's height) as page
(Sida) numbers. A folio not in the volume is looked up in the next id
given, as a part I register covers part II. The images are written to
`sweep/TAG-extra.tsv`.

**locate** is for household examinations without a register. Taking
the volumes in the order given (newest first), it reads whole pages
outward from FRAC of the numbered pages (0, −1, +1, −2, …, TRIES pages)
until a place heading matches a name: a short line at the top of the
page or of the form "X under Y". The hit goes to `sweep/TAG.tsv` and its
position is the starting point in the next volume, as a parish keeps
its farms in much the same order from book to book. Start FRAC from a
register's folio in a later parish book. To read a whole block (an
estate with its crofts), list the pages around each hit in
TAG-extra.tsv.

**heads** takes every STEP-th numbered image, fetches only the top
quarter of the left page (a small IIIF region, `heads/` in the volume
folder), reads it, and writes all head text to `sweep/TAG-heads.tsv` and
images whose head matches a name (ratio 0.8) to `sweep/TAG.tsv`. Slow
(the printed column titles fill the strip) and blind to farms named
further down the page; `locate` worked better on one parish.

**pages** fetches the images in TAG.tsv and TAG-extra.tsv, their
neighbours (PAD) and the gaps between matches up to six images, at WIDTH
px into the volume folder as shelf(1) does, and reads them whole
(`ocr/*.vision.tsv`, `*.trocr.tsv`).

**report** prints the read text of the same pages `pages` reads, per
volume and page, in reading order: raw, with the model's errors, for a
person (or a model) to condense and check against the images.

Tried on one parish (household examinations 1771–1900, parish books
1901–1950): registers gave the 1901+ folios directly; `locate` found an
estate's block in 19 of 21 older books; TrOCR's text was good enough
to condense households, roles and years, poor before about 1810.

About 3 s a head and 50 s a page on Apple MPS; requests one at a time,
as shelf(1). Stops when free disk falls below FLOOR.

## FILES

Under the shelf (`<data_dir>/archive`, shared between families; shelf(1)): the volume folders, `cookie.txt` (login
volumes), `sweep/TAG.tsv`, `TAG-heads.tsv`, `TAG-extra.tsv`.

## SEE ALSO

shelf(1), fetch(1), `experiments/register_ocr/README.md`
