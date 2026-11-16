# SHELF(1)

## NAME

experiments/register_ocr/shelf.py — keep cited archive volumes locally as a readable shelf (sketch)

## SYNOPSIS

    python3 shelf.py fetch [--phases 1,3,4,2,5,6] [--floor-gb 15] [--root DIR]
    python3 shelf.py index [--root DIR]
    python3 shelf.py ocr [--follow] [--root DIR]
    python3 shelf.py frontmatter [--root DIR]

## DESCRIPTION

A sketch, unvalidated. It keeps a personal copy of the Riksarkivet
volumes the tree cites: not a cache, but a store to browse and to build
presentations from. The volumes are those in `data/output/volume_refs.csv`
(`ra_images`) and in `data/cache/iiif/volumes.tsv`.

`fetch` works breadth first: each phase covers every volume before the
next begins, phases in the order given (default 1, 3, 4, 2, 5: cited and
index pages before covers), with older volumes first and the most cited
first among them. Each image fetched or failed is one line on stdout.

1. The IIIF manifest: page labels ("Bild N / Sida M") and Riksarkivet's
   structure (parish / record type / years → image ranges).
2. Covers: images 1, 2 and the last one, full size.
3. Cited images and the image after each, full size.
4. Index pages: structure ranges named register, index, innehåll,
   förteckning or alfabet, full size.
6. Scout: the last three images before the first page number, and
   spines (images over 2.5 times wider than high), 1000 px wide into
   `scout/`. Spines stay small, as illustration.
7. Unpaginated images between numbered pages: not in the default run.
8. Full size for the scouted images `frontmatter` classes as cover or
   index. Run `ocr` and `frontmatter` between 6 and 8.
5. Thumbnails 200 px wide of the images between a volume's first and
   last pertinent (cited or index) image: blurry stand-ins for the pages
   not kept.

A rerun skips files already on disk. One request at a time, about one
per second, with the viewer as Referer. Network errors are retried with
back-off. The run stops when free disk falls below `--floor-gb`.

Volumes younger than about 110 years need a login. A cookie header in
`ROOT/cookie.txt` is sent with each request (from a browser export,
cookies for `.riksarkivet.se`). Without it, or once it expires, the first
401 in a volume skips the rest of that volume and is listed in
`pending-login.tsv`; rerun with a fresh cookie.

`ocr` runs Apple Vision (`vision.swift`, compiled once into
`ROOT/.bin/vision`) on each full-size image that has no output yet: raw
and untuned, kept for later passes. `--follow` polls every ten minutes
while `fetch` adds images and stops after an idle day.

A second pass, `experiments/register_ocr/htr.py ROOT [--follow]` (run with
`~/.cache/sg-htr-venv/bin/python`, `HF_HUB_OFFLINE=1`), re-reads Vision's
line boxes with Riksarkivet's TrOCR handwriting model into `.trocr.tsv`
beside each Vision file, skipping covers and typed pages. About 50 s a page.

`frontmatter` classes each unpaginated image with Vision text as spine
(by shape), target (filming cards and Riksarkivet's notes and labels:
BEGIN/BÖRJAN, county and date, SVAR, volymnummer), form (printed tables
such as Barnhusbarn or Folkmängden), cover (few short lines, or a title
page: Församlingsbok, Husförhörs-Bok, …bok within the first three lines
of at most twelve), index (15 lines or more, most with digits; mostly
farm registers), other or blank, into `frontmatter.tsv`. Rough rules,
spot-checked on text only, unvalidated. `htr.py` reads unpaginated pages
only when classed as index, and leaves typed or printed pages (Vision
confident on 80% of the lines) to Vision.

`index` writes `ROOT/README.md` (one row per volume, images held) and
`structure.tsv`.

## FILES

ROOT is `data/archive` (git-ignored) unless `--root` is given.

- `<Arkiv>/<ref> <serie> (<dates>) <id>/`: `manifest.json.gz`,
  `volume.md` (catalogue fields, viewer link, cited images, structure),
  `Bild NNNN - Sida M.jpg`, `thumbs/`, `scout/` (with its own `ocr/`), `ocr/Bild NNNN - Sida M.vision.tsv` and `.trocr.tsv`
  (one text line per row: box x y w h as page fractions from top left,
  tab, three candidates `text|confidence`).
- `structure.tsv`: volume, reference, archive, series, dates, images,
  section, first and last image. Structure only, no person data.
- `frontmatter.tsv`: volume, reference, image, front or inner, lines,
  kind, the three tallest lines' text.
- `log.tsv`, `pending-login.tsv`, `cookie.txt`, `.bin/vision`.

## SEE ALSO

fetch(1), volumes(1), riksarkivet(1), serve(1) (browse the shelf)
