# MAPLAYERS(1)

## NAME

maplayers.py — dated map layers (old maps, aerial photos) for the geography view

## SYNOPSIS

    python3 maplayers.py [--list]

## DESCRIPTION

Reads the downloaded maps in `data/input/maps/`, cuts each to its map
frame and places it: an image per layer in `data/cache/maps/` and
`maps.json`, which lists each layer's label, year, source file, grid,
frame and the latitude and longitude of its north-west, north-east and
south-west corners. serve(1) serves the folder under `/maps/`; the
geography view then offers the layers in a switcher at its top right, with
one opacity slider for all, drawn under the events. Without the folder the
view is as before. Rebuild after adding maps; the run replaces the folder's
`maps.json`.

Two kinds of input are recognised; other files are listed and skipped:

- **Lantmäteriet print-outs** (PDF with "SWEREF 99 TM" in the text): the
  corners come from the text layer (`N 6400100`, `E 401000`), the map from
  the page's embedded raster, which must fill the frame (aspect within 1 %).
- **Ekonomiska kartan scans** from Lantmäteriet's "Historiska kartor"
  (JPEG or TIFF named `…rak2_<hex>_…`; the hex spells the archive id, e.g.
  `RAK_J133-12F3b60`): the sheet name gives its 5 × 5 km square in RT 90
  (50 km square 12F, 5 km square 3b, edition 60). The map image's edges
  are found by colour and the sheet is warped square, 3000 px across. The
  TIFF is used when both it and a JPEG are there.

Year: a four-digit year in the file name, else the sheet's edition, else
the PDF's creation year (a print of today's map). Grids are converted with
Lantmäteriet's Gauss–Krüger formulas on GRS80; no GDAL.

Unvalidated: sheets other than 1:10 000 (northern Sweden's 1:20 000), and
the 1950s sheets' RT 38 grid, taken as RT 90. Generalstabskartan and
häradsekonomiska kartan scans need control points and are skipped.

## OPTIONS

`--list` — print what each input file would become (kind, label, year);
write nothing.

## FILES

Reads `data/input/maps/`. Writes `data/cache/maps/` (images and
`maps.json`). The maps show family property: they stay in `data/`.
Needs `pdftotext`, `pdfimages` and `pdfinfo` (poppler), Pillow and numpy.

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml` (and so its folders).

## EXAMPLES

    python3 maplayers.py --list
    python3 maplayers.py && python3 serve.py

## SEE ALSO

serve(1), `geoview.py`, `docs/data.md`
