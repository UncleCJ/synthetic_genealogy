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
and `w,` sizes only. `pct:` regions are not supported.
Wrong arguments, or FIRST after LAST, print the usage.

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

### Finding one entry in a volume

How a death and burial entry was found, page by page, in the 2026-11
death-book pass (the same works for births, marriages or a household).
About three to five images per person; skim small, read large.

1. **Which volume.** The event's parish and year give the archive
   (`riksarkivet.py <parish>`) and, in its inventory, the volume whose
   years cover the event: series F (deaths and burials), or C where births,
   marriages and deaths share a book. Catalogue years can mislead: a C
   volume catalogued 1861–1877 kept its death pages in use to 1888, and
   the next C volume held births only. When the year is not where it
   should be, try the neighbouring volume of the series.
2. **Where in it.** `riksarkivet.py "<code>"` gives the image series and,
   through the manifest, the image count. A combined C volume runs births,
   then marriages, then deaths, each a block of its own; a printed page of
   instructions ("Anvisningar … Död- och Begrafnings-Bok") opens the death
   block. Estimate the image from the years (a small rural parish fills
   one image a year or less; a large one two or three), and skim one:

        python3 fetch.py SERIESID 60 60 full 800, img

3. **Bisect on the year.** Printed forms carry it in the header
   ("18__ års Död- och Begrafnings-Bok", the last two digits by hand);
   older ledgers have handwritten headings ("Döde år 1847") inside the
   page. Step back or forward by the years missed; two or three skims
   usually land on the year. A thin top strip is enough to read a header.
4. **The entry.** Entries run by date of death within the year. Fetch the
   one image large (`2400,`) and crop locally rather than fetching regions
   again. Check the age at death against the expected birth date: an
   exact fit (years, months, days) identifies the person better than the
   spelling of the name.
5. **Write down what you saw.** Image number, printed page and years per
   image go into the volume index (`data/cache/iiif/volumes.tsv`), so the
   next search in the same volume starts there.

An image that answers 401 is login-only: material younger than about 110
years, judged by the volume's last year (volumes ending 1915–1918 were
closed in 2026). A login in the viewer is the only way in.

## SEE ALSO

riksarkivet(1), `experiments/register_ocr/README.md`, `docs/records.md`
