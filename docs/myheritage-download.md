# Downloading shared segments from MyHeritage

*På svenska: [myheritage-download.sv.md](myheritage-download.sv.md).*

A cheat sheet for anyone sharing their MyHeritage DNA matches with the
project. MyHeritage no longer exports all matches at once, so segments come
from the one-to-many chromosome browser, a few chosen matches at a time.

## The usual way

For each tester (kit):

1. **DNA → DNA Matches**, and pick the kit in the menu at the top.
2. **DNA tools → Chromosome Browser**, one-to-many.
3. **Add matches**: the ones you are asked about (about seven per round).
4. **Download shared DNA info**: a CSV file.
5. Rename it `<Tester> <YYYY-MM-DD> <original name>.csv`, for example
   `Anna 2026-11-10 shared_dna_segments.csv`.

Repeat steps 3–5 for the next matches, then for the next tester. Send the
files as they are, privately (not on a forum): DNA data is sensitive.

## Good to know

- **The same key matches for every tester** (a known cousin on each side,
  say) make the files comparable across siblings.
- **Don't open and save the file in Excel**: it can garble å, ä, ö and the
  columns. Send the downloaded file untouched.
- Rows whose match is called **"All selected DNA Matches"** are segments
  shared with all the chosen matches at once (triangulated). Leave them in;
  they are read separately.

## If something's missing

- **Matches are locked** (blurred names, "Unlock"): the kit needs a paid
  plan or a one-off unlock before its segments can be seen or downloaded.
- **A kit isn't in the menu**: it belongs to another account. Ask its owner
  to make you a manager of it, or to download its files themselves.
- **A match can't be found**: search by the name it uses on MyHeritage,
  which may differ from the one in the tree.

The menu and button names were written from memory and may have changed.
How the files are read: `myheritage_io.py`.
