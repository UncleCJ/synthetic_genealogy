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
   and place; one that cannot is kept on the person, noted in
   `tree_notes.md`.
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
    python3 pipeline.py          # errata report, family lens

Set `export TREE_WHO=<your initials>` once per shell, so edits are signed.

## SEE ALSO

intro(1) (every tool), errata(5), tree_store(1), store_query(1), `docs/records.md` ("Errata",
"The tree store"), `research/README.md`
