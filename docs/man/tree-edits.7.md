# TREE-EDITS(7)

## NAME

tree-edits — where a change to the family tree goes, and how it survives the next export

## DESCRIPTION

MyHeritage is the master tree. Nothing here edits it; changes are kept
beside it, keyed so they survive a new export, and checked every run.
Three places, by what the change is:

| The change | Goes to | Tool | Page |
|---|---|---|---|
| MyHeritage says something wrong (page, volume, parish, birth, death) | `data/notes/errata.toml`, `[[fix]]` | your editor | errata(5) |
| A remark to see wherever a record, image, volume, person or place appears | `data/notes/errata.toml`, `[[note]]` | your editor | errata(5) |
| Something MyHeritage does not hold: a new source (letter, memoir, photo), an event from it, a citation, a DNA match linked to a person | the store, `data/store/tree_edits.json` | `tree_store.py` | tree_store(1) |
| A question, hypothesis or finding, with its reasoning | `data/notes/research/<id>.md` | `research_log.py` | `research/README.md` |

Rule of thumb: **correcting** something imported is an erratum; **adding**
something is a store edit. The store refuses to change or drop imported
rows and says so.

A `[[note]]` saying *to cite: …* is a fine first step when the source is
not yet transcribed; turn it into `add-source` and `cite` once it is.

## LIFE OF A CHANGE

1. You make it (errata.toml by hand; store edits by `tree_store.py`, each
   one appended to `data/store/tree_notes.md` with its `--why`).
2. Each run checks errata against the current export
   (`data/output/errata_report.md`): **applied**, **retired** (MyHeritage
   now agrees: fix it upstream at leisure, then delete the entry),
   **conflict** (MyHeritage says a third thing), **orphan** (the key is gone).
3. A new MyHeritage export: `tree_store.py import-tree` replaces the
   imported rows and replays every store edit from `tree_edits.json`.
   Citations of imported events find their event again by owner, tag, date
   and place, or by owner, tag and date alone when only one event fits (an
   export may rewrite the place text); one that cannot is kept on the
   person, noted in `tree_notes.md`.
4. `backup.py status` / the backup routine keeps `notes/` and the two store
   text files; `tree.sqlite` itself is rebuildable.

## WORKFLOW

    # 1. who and what
    python3 store_query.py find "anna exempel"
    python3 store_query.py person MH:I123
    # 2. the change (one of)
    $EDITOR data/notes/errata.toml
    python3 tree_store.py add-source ... ; python3 tree_store.py cite ...
    # 3. see it
    python3 tree_store.py notes | tail
    python3 pipeline.py          # errata report, family page

Set `export TREE_WHO=<your initials>` once per shell, so edits are signed.

## A NEW EXPORT

After fixing things in MyHeritage, export the tree again (by hand, or ask
a Claude session to do steps 2–6):

1. Download the GEDCOM into `data/input/`.
2. Rename it to the tree's pattern, `<tree>_<date>_<token>_A.ged`, e.g.
   `1234567-Example_2026-11-15_ab12cd_…_A.ged` (MyHeritage leaves out the
   tree and the date).
3. In `family.toml` `[gedcom]`: the new name in `file`, the old one first
   in `earlier`.
4. See what changed upstream:
   `python3 gedcom_audit.py diff data/input/OLD.ged data/input/NEW.ged`
   (people by MyHeritage id: added, removed, names, births, deaths,
   parents, and who of the removed was re-entered under a new id).
   Then record the re-entered people, so everything keyed by their old
   id follows them (errata, store edits, identities):
   `python3 gedcom_audit.py successors --keep` matches the new export
   against every `earlier` one (a person deleted in one export and
   re-entered a few exports later is found too) by given names (spelling
   folded: Gustaf/Gustav), birth and death dates, and above all shared
   parents, partners and children, and appends the pairs to
   `data/notes/successors.tsv` with status `auto`. Read the list; set a
   wrong pair to `no` (it is then never followed nor proposed again),
   a checked one to `yes`.
5. `python3 pipeline.py` (the tree feeds the anchors too; `pipeline.py
   tree` for the records side only).
6. `data/output/errata_report.md`: delete **retired** entries; an
   **orphan** whose person you removed upstream is done, delete it too
   (one whose person was re-entered belongs in successors.tsv instead);
   look again at each **conflict**.
7. Archive the export on Drive (the archive routine) and back up the
   notes.

## SEE ALSO

intro(1) (every tool), errata(5), tree_store(1), store_query(1), `docs/records.md` ("Errata",
"The tree store"), `research/README.md`
