# Gazetteer

Places this research touches, as stable entities. Geography is public
knowledge, so this folder is on the public line; the family tree that cites
these places is not.

- `parishes.toml`: parishes with the Riksarkivet reference code of their
  archive (e.g. `SE/VALA/00204`), how that code was found, Wikidata item,
  coordinates and alias spellings.
- `places.toml`: villages, farms and crofts, keyed `"Parish/Name"`, with
  `variants`, `within` (the village a farm belongs to), `kind`, `checked`.
- `cache/`: answers from Riksarkivet (volume facts by reference code,
  archive codes by parish name) and Wikidata, so reruns need no network.

`gazetteer.py build` adds entries and fills empty fields; it never
overwrites or deletes, so hand edits survive. Spelling variants are joined
by hand from the proposals it writes to a (private) to-do list. Entries
come only from household-examination citations and pre-1950 place strings,
without digits or street names.

Volumes are written as Riksarkivet writes them: series/volume, `A II a/3`.

## Data sources and terms

The gazetteer's data draws on [Wikidata](https://www.wikidata.org)
(CC0), Riksarkivet's open data, and
[OpenStreetMap](https://www.openstreetmap.org/copyright) (ODbL,
© OpenStreetMap contributors). Those terms apply to this folder's data
rather than the repository's MIT licence. `cache/geocode.json` holds
OpenStreetMap-derived coordinates.
