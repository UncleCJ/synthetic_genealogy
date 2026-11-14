# FETCH(1)

## NAME

experiments/register_ocr/fetch.py — fetch page images or regions from Riksarkivet (proof of concept)

## SYNOPSIS

    python3 fetch.py SERIES FIRST LAST REGION SIZE OUTDIR

## DESCRIPTION

A proof of concept: unvalidated, for a few pages at a time. It downloads
images FIRST to LAST (inclusive) of one image series from Riksarkivet's
IIIF image server, for the register OCR experiment
(`experiments/register_ocr/README.md`). It is not part of the pipeline.

*SERIES* is the volume's image series id, *FIRST* and *LAST* image numbers
as in the viewer link `sok.riksarkivet.se/bildvisning/<series>_<number>`.
`riksarkivet.py` gives that id (its `images` field) and the viewer link and
page span of a volume; fetch.py does not call it, you pass the id.

*REGION* is `full` or a pixel region `x,y,w,h`. *SIZE* is `full` or `w,`
(width in pixels, e.g. `1600,`). The server is IIIF level 1: pixel regions
and `w,` sizes only. The `pct:` regions the script's docstring mentions
are not supported by the server.

The server refuses requests without the viewer as Referer, so the script
sends `https://sok.riksarkivet.se/`. It waits one second after each
download. Images already on disk are not fetched again. A failed image
prints `ERR` and the run goes on. Each line printed is the image number,
file name and size in bytes. Bulk use waits on Riksarkivet's terms.

## FILES

Writes `OUTDIR/<series>_<number>_<region>_<size>.jpg` (OUTDIR is created);
punctuation in region and size is replaced, e.g. `full` and `1600,` give
`..._full_1600.jpg`.

## ENVIRONMENT

None.

## EXAMPLES

Whole images 20 to 22, 1600 pixels wide:

    python3 fetch.py SERIESID 20 22 full 1600, img

The top strip of one image (pixel region):

    python3 fetch.py SERIESID 20 20 0,0,2400,300 full strip

## SEE ALSO

riksarkivet(1), `experiments/register_ocr/README.md`, `docs/records.md`
