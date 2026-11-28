# SHELF(1)

## NAME

experiments/register_ocr/shelf.py — keep cited archive volumes locally as a readable shelf (sketch)

## SYNOPSIS

    python3 shelf.py fetch [--phases 1,3,4,6] [--floor-gb 15] [--root DIR]
    python3 shelf.py index [--root DIR]
    python3 shelf.py ocr [--follow] [--root DIR]
    python3 shelf.py rush <viewer URL> [--floor-gb 15] [--root DIR]
    python3 shelf.py frontmatter [--root DIR]
    python3 shelf.py pages [--root DIR]

## DESCRIPTION

A sketch, unvalidated. It keeps a personal copy of the Riksarkivet
volumes the tree cites: not a cache, but a store to browse and to build
presentations from. The volumes are those in the family's
`output/volume_refs.csv` (`ra_images`) and `cache/iiif/volumes.tsv`.

Two families share one shelf: the volumes, images and OCR are public
records, fetched and read once. The second family's `<data_dir>/archive`
is a link to the first's (`ln -s ../data/archive data-example/archive`),
and every tool is run with its `FAMILY_CONFIG`:

    FAMILY_CONFIG=data-example/family.toml python3 shelf.py fetch --phases 1,3

`fetch` and `rush` get that family's volumes; `volume.md`, `index` and
`frontmatter` cover the cited images of every family listed in
`families.txt`. Which people cite a page stays in each family's own files
(rows(1)).

`fetch` works breadth first: each phase covers every volume before the
next begins, phases in the order given (default 1, 3, 4, 6: cited and
index pages first), with older volumes first and the most cited
first among them. Each image fetched or failed is one line on stdout.

1. The IIIF manifest: page labels ("Bild N / Sida M") and Riksarkivet's
   structure (parish / record type / years → image ranges).
2. Images 1, 2 and the last one, full size: filming cards and inside
   covers, not in the default run (the outside and spine are scouted).
3. Cited images and the image after each, full size. A citation with
   only a page number (MyHeritage's) is mapped to the image Riksarkivet
   labels with that page, or, where Riksarkivet labels a spread by its
   left page only, the image labelled one lower. A page no label names
   gets three guessed images, on a line through the nearest labels (two on
   one side past the first or last label; none past the volume's end);
   past the last label of a volume labelled one page an image, nine
   around half the page (MyHeritage counts sides there),
   for rows(1) to look for the person on; `volume.md` lists these separately ("sida →
   bild", or no label when Riksarkivet has none).
4. Index pages: structure ranges named register, index, innehåll,
   förteckning or alfabet, full size.
6. Scout: the last three images before the first page number, and
   spines (images over 2.5 times wider than high), 1000 px wide into
   `scout/`. Spines stay small, as illustration.
7. Unpaginated images between numbered pages: not in the default run.
8. Full size for the scouted images `frontmatter` classes as index;
   covers and spines stay at scout size. Run `ocr` and `frontmatter`
   between 6 and 8.
5. Thumbnails 200 px wide of the images between a volume's first and
   last pertinent (cited or index) image: blurry stand-ins for the pages
   not kept. Not in the default run (tens of thousands of requests);
   `thumbs/` may be deleted when space is short, the viewer then links
   those pages to Riksarkivet.

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

`rush` takes one image now, from a viewer link
(`sok.riksarkivet.se/bildvisning/<volume>_<image>`, or an IIIF
`arkis!<volume>_<image>` URL): the manifest and `volume.md` if the volume
is new, the image full size, and its Vision text, stored as `fetch` and
`ocr` store them. It prints the image and Vision file paths.

A second pass, `experiments/register_ocr/htr.py ROOT [--follow] [--only TEXT] [--cited]` (run with
`~/.cache/sg-htr-venv/bin/python`, `HF_HUB_OFFLINE=1`), re-reads Vision's
line boxes with Riksarkivet's TrOCR handwriting model into `.trocr.tsv`
beside each Vision file, skipping covers and typed pages. About 50 s a page.
`--only TEXT` reads just the Vision files whose path contains TEXT (say
`C0023142/ocr/Bild 0062`), covers and unclassed pages included.
`--cited` reads just the images the family in `FAMILY_CONFIG` cites (what
rows(1) reads), so a second family on the shelf need not wait for the rest.

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

`pages` writes `pages.tsv`: the page number written on each held image
beside Riksarkivet's label. Numbers in the outer top corners, years left
out, vote for a line page = image + b, or 2 × image + b for spreads; a
line two or more images agree on is a run, so a single misreading is
outvoted, and images inside a run get the fitted number when nothing was
read, unless that number was read on another image, or an image between
the run's nearest readings has a label read on it that the run
contradicts (a run of two stray readings far apart then fills nothing).
A label read on the page wins. Verdicts: agrees, label differs,
no label, each with ", fitted" when not read on that image; read, no
run; unread. Unvalidated.

`index` writes `ROOT/README.md` (one row per volume, images held) and
`structure.tsv`.

## FILES

ROOT is `<data_dir>/archive` of the family in `FAMILY_CONFIG` (default
`family.toml`, so `data/archive`; git-ignored) unless `--root` is given.

- `<Arkiv>/<ref> <serie> (<dates>) <id>/`: `manifest.json.gz`,
  `volume.md` (catalogue fields, viewer link, cited images, structure),
  `Bild NNNN - Sida M.jpg`, `thumbs/`, `scout/` (with its own `ocr/`), `ocr/Bild NNNN - Sida M.vision.tsv` and `.trocr.tsv`
  (one text line per row: box x y w h as page fractions from top left,
  tab, three candidates `text|confidence`).
- `structure.tsv`: volume, reference, archive, series, dates, images,
  section, first and last image. Structure only, no person data.
- `frontmatter.tsv`: volume, reference, image, front or inner, lines,
  kind, the three tallest lines' text.
- `pages.tsv`: volume, image, Riksarkivet's label, page written,
  verdict, numbers read.
- `families.txt`: the data folders sharing the shelf, one a line (a
  family is added on its first run).
- `log.tsv`, `pending-login.tsv`, `cookie.txt`, `.bin/vision`.

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml` (its citations, and its
`archive` link as the default ROOT).

## SEE ALSO

fetch(1), volumes(1), riksarkivet(1), serve(1) (browse the shelf)
