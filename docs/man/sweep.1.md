# SWEEP(1)

## NAME

experiments/register_ocr/sweep.py — find a place's pages in whole volumes, then read them (sketch, unvalidated)

## SYNOPSIS

    PY=~/.cache/sg-htr-venv/bin/python; export HF_HUB_OFFLINE=1
    $PY sweep.py register TAG ID... --names "Name,Variant" [--width 2600] [--floor-gb 5]
    $PY sweep.py heads TAG ID... --names "Name,Variant" [--step 3] [--floor-gb 5]
    $PY sweep.py pages TAG [--pad 1] [--width 2600] [--floor-gb 5]
    python3 sweep.py report TAG

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

**heads** takes every STEP-th numbered image, fetches only the top
quarter of the left page (a small IIIF region, `heads/` in the volume
folder), reads it, and writes all head text to `sweep/TAG-heads.tsv` and
images whose head matches a name (ratio 0.8) to `sweep/TAG.tsv`. For
household examinations headed by rote or village on every page; parish
books name a property only on its first page, so use `register` there.
Look through TAG-heads.tsv for the rote and add its pages to
TAG-extra.tsv by hand (id, image).

**pages** fetches the images in TAG.tsv and TAG-extra.tsv, their
neighbours (PAD) and the gaps between matches up to six images, at WIDTH
px into the volume folder as shelf(1) does, and reads them whole
(`ocr/*.vision.tsv`, `*.trocr.tsv`).

**report** prints the read text per volume and page, in reading order:
raw, with the model's errors, for a person to read and check against the
images.

About 3 s a head and 50 s a page on Apple MPS; requests one at a time,
as shelf(1). Stops when free disk falls below FLOOR.

## FILES

Under `data/archive` (shelf(1)): the volume folders, `cookie.txt` (login
volumes), `sweep/TAG.tsv`, `TAG-heads.tsv`, `TAG-extra.tsv`.

## SEE ALSO

shelf(1), fetch(1), `experiments/register_ocr/README.md`
